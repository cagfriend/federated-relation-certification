"""Crash-stop, single-fault, reliable-memory simulator with an atomic commit barrier.

Not a network consensus algorithm: membership/failure detection is supplied by
the injector. No fault is allowed during the final atomic commit decision.
All transferred state is decoded from counted packets, never copied remotely.
"""
from collections import Counter
import hashlib
import json
import struct

import numpy as np

from experiments.public_scaling.codec import (Message, SETUP, COMMIT, EMPTY, FULL,
    UP, DOWN, UNKNOWN, DecodeError, encode_vector, decode_vector,
    acknowledgement, check_ack, validate_context)

POLICIES=('rebuild','on_demand','hot_backup')


def digest(array):return hashlib.sha256(array.tobytes()).hexdigest()


class Node:
    def __init__(self):
        self.own=None;self.counts=None;self.version=UNKNOWN;self.term=1
        self.rows={};self.rows_version=UNKNOWN
        self.pending=None


class RecoveryProtocol:
    def __init__(self,edges,samples,dimensions,policy):
        if policy not in POLICIES:raise ValueError('Unknown policy')
        self.policy=policy;self.edges=edges;self.samples=samples;self.dimensions=dimensions
        self.length=len(edges);self.clients=len(dimensions)
        if not 3<=self.clients<=255:raise ValueError('Need 3..255 clients')
        self.graph_id=hashlib.sha256(edges.astype('<u4').tobytes()).digest()[:16]
        self.nodes=[Node() for _ in dimensions];self.active=list(range(self.clients))
        self.leader=0;self.backup=1;self.term=1;self.version=UNKNOWN
        self.ledger=Counter();self.sent_packets=[];self.capture=False
        self.staged={};self.seen={};self.current_category='normal'
        self.force_full=False
        self.replica_ack_client=None;self.replica_ack_version=UNKNOWN
        self._register()

    def _wire(self,packet,src,dst,category=None):
        if src==dst:raise ValueError('Local work is not a wire message')
        msg=Message.from_bytes(packet)
        if msg.term!=self.term:raise DecodeError('Stale/future term')
        category=category or self.current_category
        self.ledger['bytes']+=len(packet);self.ledger['messages']+=1
        self.ledger[category+'_bytes']+=len(packet);self.ledger[category+'_messages']+=1
        if self.capture:self.sent_packets.append((packet,src,dst,category))
        return Message.from_bytes(bytes(packet))

    def _deliver(self,packet,src,dst,category=None):
        msg=self._wire(packet,src,dst,category)
        ack=acknowledgement(packet,dst)
        self._wire(ack,dst,src,category);check_ack(ack,packet,sender=dst)
        return msg

    def _control(self,kind,src,dst,body,category):
        packet=Message(kind,EMPTY,0,self.term,self.version,self.version,src,
                       self.length,0,self.graph_id,body).to_bytes()
        received=self._deliver(packet,src,dst,category)
        validate_context(received,graph_id=self.graph_id,term=self.term,base=self.version,
                         target=self.version,sender=src,kind=kind)
        if received.body!=body:raise DecodeError('Control payload changed')

    def _register(self):
        metadata=json.dumps(dict(samples=self.samples,dimensions=self.dimensions,
                                  sample_ids='0..M-1',edges=self.length),sort_keys=True).encode()
        body=struct.pack('<I',len(metadata))+metadata+self.edges.astype('<u4').tobytes()
        for client in self.active:
            if client==self.leader:continue
            self._control(SETUP,self.leader,client,body,'setup')
            offset=4+struct.unpack('<I',body[:4])[0]
            if not np.array_equal(np.frombuffer(body[offset:],dtype='<u4').reshape(-1,2),self.edges):
                raise DecodeError('Graph registration failed')

    def _batch_rows(self,src,dst,rows,previous,base,target,category,receiver_previous=None):
        """One framed packet plus ACK; nested per-client vectors are counted too."""
        transferred=sorted(c for c in rows if c!=dst)
        parts=[struct.pack('<I',len(transferred))]
        for c in transferred:
            old=None if previous is None else previous.get(c)
            packet=encode_vector(rows[c],old,kind=UP,adaptive=True,graph_id=self.graph_id,
                sender=c,base=UNKNOWN if old is None else base,target=target,maximum=1,term=self.term)
            parts.extend((struct.pack('<II',c,len(packet)),packet))
        packet=Message(SETUP,FULL,0,self.term,base,target,src,self.length,
                       len(transferred),self.graph_id,b''.join(parts)).to_bytes()
        received=self._deliver(packet,src,dst,category)
        validate_context(received,graph_id=self.graph_id,term=self.term,base=base,
                         target=target,sender=src,kind=SETUP)
        body=received.body;offset=4;count=struct.unpack('<I',body[:4])[0]
        if previous is not None and self.nodes[dst].rows_version!=base:
            raise DecodeError('Replica does not hold the acknowledged version')
        if count!=len(transferred):raise DecodeError('Batch length mismatch')
        decoded={dst:self.nodes[dst].own.copy()}
        seen=set()
        for _ in range(count):
            c,size=struct.unpack('<II',body[offset:offset+8]);offset+=8
            if c not in transferred or c in seen:raise DecodeError('Repeated/unknown row')
            seen.add(c);inner=body[offset:offset+size];offset+=size
            # Decoder uses the recipient's actual state. Encoder's previous
            # rows above must be sender-owned, not read remotely for free.
            inner_msg=Message.from_bytes(inner)
            old=None if inner_msg.base==UNKNOWN else (receiver_previous or {}).get(c)
            row,_=decode_vector(inner,old,graph_id=self.graph_id,sender=c,
                base=inner_msg.base,target=target,length=self.length,
                maximum=1,kind=UP,term=self.term)
            decoded[c]=row
        if offset!=len(body) or seen!=set(transferred):raise DecodeError('Malformed batch')
        # Compare the actual decoded transfer, not a remote shared reference.
        if set(decoded)!=set(rows) or any(not np.array_equal(decoded[c],rows[c]) for c in rows):
            raise DecodeError('Transferred checkpoint differs')
        return decoded

    def _elect(self,exclude):
        candidates=[c for c in self.active if c!=exclude]
        if not candidates:raise ValueError('No live candidate')
        candidate=min(candidates);self.term+=1
        descriptor=json.dumps(dict(candidate=candidate,members=self.active),sort_keys=True).encode()
        # Each survivor votes once for the deterministic candidate. Reliable
        # membership and no concurrent election are explicit simulator inputs.
        for c in self.active:
            if c==candidate:continue
            self._control(SETUP,candidate,c,descriptor,'election')
            self._control(COMMIT,c,candidate,descriptor,'election')
        for c in self.active:
            self.nodes[c].term=self.term
            if c!=candidate:self._control(COMMIT,candidate,c,descriptor,'election')
        self.leader=candidate;self.backup=min(c for c in self.active if c!=candidate)

    def transition(self,event):
        """Abort an uncommitted round, fence the old leader, then elect."""
        old=self.leader;graceful=event=='handoff'
        self.rollback()
        if not graceful:
            self.active.remove(old)
            # Crash destroys all process-owned state; rejoin has no hidden cache.
            self.nodes[old]=Node()
        self._elect(old)
        new=self.nodes[self.leader]
        if self.policy=='hot_backup' and new.rows_version==self.version and new.rows:
            new.rows={c:new.rows[c] for c in self.active}
        elif graceful and self.policy in ('on_demand','hot_backup'):
            donor=self.nodes[old]
            new.rows=self._batch_rows(old,self.leader,donor.rows,None,UNKNOWN,self.version,'handoff')
            new.rows_version=self.version
        else:
            # A cold rebuild uses current contributions on retry, not old rows
            # followed by another avoidable data upload.
            new.rows={};new.rows_version=UNKNOWN
        self.force_full=not bool(new.rows)
        # Explicit recovery request: senders learn whether to use their own
        # committed reference or to send current full vectors after a cold loss.
        body=json.dumps(dict(full_current=self.force_full,version=self.version),sort_keys=True).encode()
        for c in self.active:
            if c!=self.leader:self._control(SETUP,self.leader,c,body,'recovery_request')
        self.replica_ack_client=None;self.replica_ack_version=UNKNOWN
        # Never reuse stale server caches on arbitrary non-role clients.
        for c in self.active:
            if c!=self.leader and c!=self.backup:
                self.nodes[c].rows={};self.nodes[c].rows_version=UNKNOWN
        return old

    def rejoin(self,client):
        if client in self.active:raise ValueError('Already active')
        self.active.append(client);self.active.sort()
        self.nodes[client]=Node();self.nodes[client].term=self.term
        body=json.dumps(dict(rejoin=client,members=self.active),sort_keys=True).encode()
        for c in self.active:
            if c!=self.leader:self._control(SETUP,self.leader,c,body,'membership')
        # Graph/public samples remain preprovisioned across process restart.

    def rollback(self):
        self.staged={};self.seen={}
        for c in self.active:self.nodes[c].pending=None

    def accept_upload(self,packet,client):
        if client not in self.active or client==self.leader:
            raise DecodeError('Upload sender is not an active remote client')
        leader=self.nodes[self.leader]
        previous=leader.rows.get(client)
        base=UNKNOWN if previous is None else self.version
        target=0 if self.version==UNKNOWN else self.version+1
        value,_=decode_vector(packet,previous,graph_id=self.graph_id,sender=client,
            base=base,target=target,length=self.length,maximum=1,kind=UP,term=self.term)
        packet_hash=hashlib.sha256(packet).digest()
        if client in self.seen and self.seen[client]!=packet_hash:
            raise DecodeError('Conflicting duplicate upload')
        self.seen[client]=packet_hash;self.staged[client]=value
        return value

    def exchange(self,current,*,fault=None):
        """Return False after injected precommit failure, with no applied targets."""
        if fault not in (None,'crash_upload','crash_down'):raise ValueError('Unknown fault')
        self.rollback();leader=self.nodes[self.leader]
        previous_primary_rows=leader.rows
        previous_version=self.version
        target=0 if self.version==UNKNOWN else self.version+1
        remote=[c for c in self.active if c!=self.leader]
        for position,c in enumerate([self.leader]+remote):
            previous=leader.rows.get(c)
            if c==self.leader:self.staged[c]=current[c].copy()
            else:
                # Sender's base is its own committed row, but cold recovery
                # explicitly requests full encoding if the leader lacks a row.
                own=self.nodes[c].own
                if previous is not None and (own is None or not np.array_equal(previous,own)):
                    raise DecodeError('Sender/leader reference mismatch')
                sender_base=None if self.force_full else own
                packet=encode_vector(current[c],sender_base,kind=UP,
                    adaptive=True,graph_id=self.graph_id,sender=c,
                    base=UNKNOWN if sender_base is None else self.nodes[c].version,target=target,
                    maximum=1,term=self.term)
                self._deliver(packet,c,self.leader)
                self.accept_upload(packet,c)
            if fault=='crash_upload' and position==1:return False
        counts=np.sum([self.staged[c] for c in self.active],axis=0,dtype=np.int64).astype(np.uint8)
        for position,c in enumerate([self.leader]+remote):
            node=self.nodes[c]
            if c==self.leader:received=counts.copy()
            else:
                packet=encode_vector(counts,node.counts,kind=DOWN,adaptive=True,
                    graph_id=self.graph_id,sender=self.leader,
                    base=UNKNOWN if node.counts is None else node.version,target=target,
                    maximum=self.clients,term=self.term)
                self._deliver(packet,self.leader,c)
                received,_=decode_vector(packet,node.counts,graph_id=self.graph_id,sender=self.leader,
                    base=UNKNOWN if node.counts is None else node.version,target=target,
                    length=self.length,maximum=self.clients,kind=DOWN,term=self.term)
            node.pending=received
            if fault=='crash_down' and position==1:return False
        body=hashlib.sha256(counts.tobytes()).digest()
        for c in remote:self._control(COMMIT,self.leader,c,body,'commit')
        # Atomic barrier is the declared failure-model boundary. It is not
        # production atomic broadcast and not protection against partitions.
        leader.rows={c:self.staged[c].copy() for c in self.active};leader.rows_version=target
        for c in self.active:
            node=self.nodes[c]
            if node.pending is None or not np.array_equal(node.pending,counts):
                raise DecodeError('Student received incorrect pending target')
            node.own=self.staged[c].copy();node.counts=node.pending;node.pending=None;node.version=target
        self.version=target;self.rollback()
        self.force_full=False
        if self.policy=='hot_backup':self.replicate(previous_primary_rows,previous_version)
        else:
            for c in self.active:
                if c!=self.leader:self.nodes[c].rows={};self.nodes[c].rows_version=UNKNOWN
        return True

    def replicate(self,previous_primary_rows,previous_version):
        # Synchronize *after* commit, before permitting the next injected fault.
        # Replica loss/delay during this barrier is outside the single-fault model.
        self.backup=min(c for c in self.active if c!=self.leader)
        replica=self.nodes[self.backup];primary=self.nodes[self.leader]
        # Knowledge of the acknowledged replica version is held by the primary.
        # Its previous committed rows are the encoder reference; no remote read
        # of backup arrays is used to decide or encode a delta.
        acknowledged=(self.replica_ack_client==self.backup and self.replica_ack_version==previous_version)
        previous=previous_primary_rows if acknowledged and previous_primary_rows else None
        replica.rows=self._batch_rows(self.leader,self.backup,primary.rows,previous,
            previous_version if previous is not None else UNKNOWN,self.version,'replication',
            receiver_previous=replica.rows)
        replica.rows_version=self.version
        self.replica_ack_client=self.backup;self.replica_ack_version=self.version
        for c in self.active:
            if c not in (self.leader,self.backup):self.nodes[c].rows={};self.nodes[c].rows_version=UNKNOWN

    def persistent_bytes(self):
        arrays=[]
        for node in self.nodes:
            arrays.extend([node.own,node.counts,node.pending]);arrays.extend(node.rows.values())
        seen=set();total=0
        for a in arrays:
            if a is not None and id(a) not in seen:seen.add(id(a));total+=a.nbytes
        return total
