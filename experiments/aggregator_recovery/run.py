"""Protocol-only controlled traces: handoff, precommit crash and rejoin."""
import argparse
from collections import Counter
from dataclasses import dataclass,asdict
import csv
import json
import math
from pathlib import Path
import statistics as st
import sys
from time import perf_counter

import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.graphs import make_graph
from experiments.public_scaling.certification import hard_relations
from experiments.public_scaling.data import sha,source_hashes
from experiments.public_scaling.util import seal_payload,validate_payload,load_json
from .protocol import RecoveryProtocol,POLICIES,digest

ROOT=Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Case:
    name:str
    event:str='none'
    degree:int=1
    change:float=.001
    samples:int=4096
    rounds:int=200
    clients:int=6
    rejoin_after:int=3
    frequent:bool=False

    def events(self):
        if self.event=='none':return []
        if self.frequent:return list(range(max(3,self.rounds//10),self.rounds,max(3,self.rounds//10)))
        if self.event=='handoff':return sorted(set((max(3,self.rounds*3//10),max(4,self.rounds*13//20))))
        return [max(3,self.rounds*3//10)]


def plan(preset):
    settings=dict(samples=32,rounds=10,rejoin_after=2) if preset=='smoke' else {}
    return [Case(name='control_sparse',**settings),
            Case(name='handoff_sparse',event='handoff',**settings),
            Case(name='crash_upload_sparse',event='crash_upload',**settings),
            Case(name='crash_down_sparse',event='crash_down',degree=8,**settings),
            Case(name='frequent_crash',event='crash_upload',degree=8,frequent=True,**settings),
            Case(name='crash_dense',event='crash_upload',degree=8,change=.2,**settings)]


def own_sources():return {p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}


def traces(cfg,seed):
    """Legitimate same-cluster vectors, not independent arbitrary edge flips.

    These labels are synthetic cluster assignments, not private training labels.
    Each round changes a fraction of sample assignments, not edge relations.
    """
    graph=make_graph(cfg.samples,cfg.degree,seed)
    rng=np.random.default_rng(seed)
    shared=rng.integers(0,10,cfg.samples)
    labels=np.tile(shared,(cfg.clients,1))
    noisy=rng.random(labels.shape)<.25
    labels[noisy]=rng.integers(0,10,noisy.sum())
    trace=[]
    for _ in range(cfg.rounds):
        change=rng.random(labels.shape)<cfg.change
        labels[change]=(labels[change]+rng.integers(1,10,change.sum()))%10
        trace.append([hard_relations(label,graph) for label in labels])
    return graph,trace


def simulate(cfg,seed,policy,graph,trace):
    started=perf_counter()
    dimensions=tuple(512 if c<cfg.clients//2 else 2048 for c in range(cfg.clients))
    protocol=RecoveryProtocol(graph,cfg.samples,dimensions,policy)
    setup_s=perf_counter()-started
    rows=[];rejoins={};checks=0
    for rnd,current in enumerate(trace,1):
        before=dict(protocol.ledger);start=perf_counter();event_seconds=0.;abort_seconds=0.
        previous_version=protocol.version
        joined=[]
        for client,due in list(rejoins.items()):
            if due==rnd:protocol.rejoin(client);joined.append(client);del rejoins[client]
        event=cfg.event if rnd in cfg.events() else None
        old_leader=protocol.leader
        if event is not None:
            recovery_start=perf_counter()
            if event!='handoff':
                committed={c:(None if protocol.nodes[c].counts is None else protocol.nodes[c].counts.copy(),
                               protocol.nodes[c].version) for c in protocol.active}
                protocol.current_category='aborted';abort_start=perf_counter()
                if protocol.exchange(current,fault=event):raise AssertionError('Injected fault did not interrupt')
                abort_seconds=perf_counter()-abort_start
                for c,(counts,version) in committed.items():
                    if protocol.nodes[c].version!=version or not np.array_equal(protocol.nodes[c].counts,counts):
                        raise AssertionError('Partial target was committed before barrier')
            failed=protocol.transition(event)
            if event!='handoff':rejoins[failed]=rnd+cfg.rejoin_after
            protocol.current_category='recovery'
            if not protocol.exchange(current):raise AssertionError('Recovery did not commit')
            event_seconds=perf_counter()-recovery_start
        else:
            protocol.current_category='normal'
            if not protocol.exchange(current):raise AssertionError('Unexpected interruption')
        seconds=perf_counter()-start
        # Oracle and summary work is excluded from protocol local timing.
        expected=np.sum([current[c] for c in protocol.active],axis=0,dtype=np.int64)
        if protocol.version!=(0 if previous_version==0xFFFFFFFF else previous_version+1):
            raise AssertionError('Round retried with duplicated/skipped commit version')
        primary=protocol.nodes[protocol.leader]
        if set(primary.rows)!=set(protocol.active):raise AssertionError('Wrong contributor membership')
        for c in protocol.active:
            node=protocol.nodes[c]
            if (not np.array_equal(primary.rows[c],current[c]) or not np.array_equal(node.counts,expected)
                    or node.version!=protocol.version or node.term!=protocol.term or node.pending is not None):
                raise AssertionError('Incorrect committed target/state')
            checks+=len(expected)
        after=dict(protocol.ledger)
        traffic={k:after.get(k,0)-before.get(k,0) for k in after}
        rows.append(dict(round=rnd,event=event,rejoined=joined,old_leader=old_leader,
                         leader=protocol.leader,term=protocol.term,version=protocol.version,
                         active=list(protocol.active),target_denominator=len(protocol.active),
                         counts_digest=digest(expected.astype(np.uint8)),
                         relation_digest=digest(np.stack([current[c] for c in protocol.active])),
                         local_seconds=seconds,recovery_seconds_including_abort=event_seconds,
                         aborted_attempt_seconds=abort_seconds,traffic=traffic,
                         persistent_array_bytes=protocol.persistent_bytes()))
    return dict(policy=policy,setup_seconds=setup_s,round_records=rows,
                traffic=dict(protocol.ledger),counts_comparisons=checks,mismatches=0)


def check_case(case,cfg,seed,identity,trace):
    validate_payload(case)
    if (case['identity']!=identity or case['config']!=asdict(cfg) or case['seed']!=seed
            or len(case['methods'])!=len(POLICIES) or {m['policy'] for m in case['methods']}!=set(POLICIES)):
        raise ValueError('Checkpoint identity differs')
    common=None
    for method in case['methods']:
        rr=method['round_records']
        if [r['round'] for r in rr]!=list(range(1,cfg.rounds+1)) or method['mismatches']!=0:
            raise ValueError('Round coverage differs')
        if not math.isfinite(method['setup_seconds']) or method['setup_seconds']<0:raise ValueError('Invalid setup time')
        reference=[];checks=0;round_traffic=Counter()
        active=list(range(cfg.clients));leader=0;term=1;returning={}
        for rnd,(row,current) in enumerate(zip(rr,trace),1):
            joined=sorted(c for c,due in returning.items() if due==rnd)
            for c in joined:active.append(c);active.sort();del returning[c]
            old=leader;event=cfg.event if rnd in cfg.events() else None
            if event:
                if event!='handoff':active.remove(old);returning[old]=rnd+cfg.rejoin_after
                leader=min(c for c in active if c!=old);term+=1
            expected=np.sum([current[c] for c in active],axis=0,dtype=np.int64).astype(np.uint8)
            if any(row[k]!=v for k,v in dict(round=rnd,event=event,rejoined=joined,old_leader=old,leader=leader,
                       term=term,version=rnd-1,active=active,target_denominator=len(active),
                       counts_digest=digest(expected),relation_digest=digest(np.stack([current[c] for c in active]))).items()):
                raise ValueError('Saved target/election/membership differs from trace oracle')
            for key in ('local_seconds','recovery_seconds_including_abort','aborted_attempt_seconds'):
                if not math.isfinite(row[key]) or row[key]<0:raise ValueError('Invalid time')
            if row['recovery_seconds_including_abort']>row['local_seconds']+1e-9:raise ValueError('Overlapping times')
            if any(not isinstance(v,int) or v<0 for v in row['traffic'].values()):raise ValueError('Invalid wire totals')
            if row['traffic']['bytes']!=sum(v for k,v in row['traffic'].items() if k.endswith('_bytes')):
                raise ValueError('Round category bytes do not sum')
            if row['traffic']['messages']!=sum(v for k,v in row['traffic'].items() if k.endswith('_messages')):
                raise ValueError('Round category messages do not sum')
            round_traffic.update(row['traffic'])
            if row['persistent_array_bytes']<=0:raise ValueError('Invalid memory')
            checks+=len(active)*len(expected)
            reference.append((row['leader'],row['term'],tuple(row['active']),row['counts_digest'],row['relation_digest']))
        if method['counts_comparisons']!=checks:raise ValueError('Incorrect oracle count')
        if common is None:common=reference
        elif reference!=common:raise ValueError('Policies use different targets')
        traffic=method['traffic']
        if any(not isinstance(v,int) or v<0 for v in traffic.values()):raise ValueError('Invalid total traffic')
        if traffic['bytes']!=sum(v for k,v in traffic.items() if k.endswith('_bytes')):
            raise ValueError('Wire category bytes do not sum')
        if traffic['messages']!=sum(v for k,v in traffic.items() if k.endswith('_messages')):
            raise ValueError('Wire category messages do not sum')
        # Only initial graph registration precedes round_records. All recovery,
        # replica reseeding, retries and membership traffic must be in a round.
        round_traffic['setup_bytes']+=traffic.get('setup_bytes',0)
        round_traffic['setup_messages']+=traffic.get('setup_messages',0)
        round_traffic['bytes']+=traffic.get('setup_bytes',0)
        round_traffic['messages']+=traffic.get('setup_messages',0)
        if round_traffic!=Counter(traffic):raise ValueError('Round traffic + setup differs from total')


def report(output,cases):
    rows=[]
    for case in cases:
        for m in case['methods']:
            events=[r for r in m['round_records'] if r['event']]
            rows.append(dict(case=case['config']['name'],seed=case['seed'],policy=m['policy'],
                total_bytes=m['traffic']['bytes'],messages=m['traffic']['messages'],
                replication_bytes=m['traffic'].get('replication_bytes',0),
                event_round_bytes=sum(r['traffic']['bytes'] for r in events),
                local_seconds_with_setup=m['setup_seconds']+sum(r['local_seconds'] for r in m['round_records']),
                recovery_seconds_with_aborted_attempts=sum(r['recovery_seconds_including_abort'] for r in events),
                max_persistent_array_bytes=max(r['persistent_array_bytes'] for r in m['round_records']),
                failure_events=len(events),counts_comparisons=m['counts_comparisons']))
    with (output/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    paired=[]
    for name in sorted({r['case'] for r in rows}):
        for policy in POLICIES[1:]:
            for metric in ('total_bytes','event_round_bytes','local_seconds_with_setup','recovery_seconds_with_aborted_attempts','max_persistent_array_bytes'):
                ratios=[]
                for seed in sorted({r['seed'] for r in rows if r['case']==name}):
                    a=next(r for r in rows if (r['case'],r['seed'],r['policy'])==(name,seed,policy))
                    b=next(r for r in rows if (r['case'],r['seed'],r['policy'])==(name,seed,'rebuild'))
                    if b[metric]:ratios.append(a[metric]/b[metric])
                paired.append(dict(case=name,policy=policy,baseline='rebuild',metric=metric,
                    median_ratio=None if not ratios else st.median(ratios),wins=sum(v<1 for v in ratios),seeds=len(ratios)))
    (output/'summary.json').write_text(json.dumps(dict(rows=rows,paired=paired),indent=2),encoding='utf-8')
    text=['# 临时聚合者交接/恢复：协议成本实验','',f'已完成{len(cases)}组配置-seed。completed.json经校验存在才算全套完成。','',
          '只研究真实序列化的内存传输协议，不是模型训练或实际网络；synthetic trace是合法同簇关系，不是已训练模型的输出。', '',
          '|场景|策略/全量重建|总字节比|故障/交接轮字节比|','|---|---|---:|---:|']
    for name in sorted({r['case'] for r in rows}):
        for p in POLICIES[1:]:
            vals=[next(r['median_ratio'] for r in paired if (r['case'],r['policy'],r['metric'])==(name,p,k))
                  for k in ('total_bytes','event_round_bytes')]
            text.append('|'+name+'|'+p+'|'+'|'.join('N/A' if v is None else f'{v:.5f}' for v in vals)+'|')
    text+=['','主比较是总字节，含setup、投票/换届、正常复制、失败尝试、重试、重新入组及ACK。事件轮字节含该轮正常数据和提交，不是纯快照大小；无事件场景用N/A。', '',
           '本地wall time是序列化/解码/状态处理时间，不含网络传播、故障检测等待、真实选举超时或模型重训练，不能叫部署恢复时延。恢复计时含失败尝试和重试至首次新目标提交；同轮公共训练不存在。', '',
           'hot_backup是扩展对照，不是当前方法默认。必须同时看正常复制成本与故障频率；不保证比rebuild或on_demand节省。只测持久数组字节，未测进程峰值或Python对象内存。', '',
           '失效成员退出目标分母，重新加入后只贡献当前轮；保存的目标摘要可由输入seed和代码重新构造核验。不覆盖提交决议传播中崩溃、网络分区、拜占庭或候补同步失败。']
    (output/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset',choices=('full','smoke'),default='full')
    ap.add_argument('--output',type=Path);ap.add_argument('--resume',action='store_true')
    args=ap.parse_args();output=(args.output or ROOT/f'experiments/aggregator_recovery/results_{args.preset}').resolve()
    configs=plan(args.preset);seeds=[404,505,606]
    identity=dict(preset=args.preset,plan=[asdict(c) for c in configs],seeds=seeds,source_hashes=own_sources(),
                  core_source_hashes=source_hashes(),runtime=dict(python=sys.version,executable=sys.executable,numpy=np.__version__),
                  failure_model='single crash-stop before atomic commit; reliable injected membership; no partition/commit-broadcast faults')
    if args.resume:
        if load_json(output/'environment.json')!=identity:raise ValueError('Resume identity changed')
    elif output.exists() and any(output.iterdir()):raise FileExistsError('Use fresh output or --resume')
    output.mkdir(parents=True,exist_ok=True)
    if not args.resume:(output/'environment.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
    cases=[]
    with threadpool_limits(limits=1):
        for seed in seeds:
            for cfg in configs:
                graph,trace=traces(cfg,seed);path=output/f'{cfg.name}_seed_{seed}.json'
                if path.exists():
                    case=load_json(path);check_case(case,cfg,seed,identity,trace)
                    print(f'Preserved {cfg.name} seed={seed}',flush=True)
                else:
                    order=list(POLICIES);shift=seed%len(order);order=order[shift:]+order[:shift]
                    methods=[simulate(cfg,seed,p,graph,trace) for p in order]
                    case=seal_payload(dict(config=asdict(cfg),seed=seed,methods=methods,identity=identity))
                    check_case(case,cfg,seed,identity,trace)
                    temporary=path.with_suffix('.json.part');temporary.write_text(json.dumps(case,indent=2),encoding='utf-8');temporary.replace(path)
                    print(f'Completed {cfg.name} seed={seed}',flush=True)
                cases.append(case);report(output,cases)
    done=dict(case_count=len(cases),policy_replays=len(cases)*len(POLICIES),mismatches=0,
              counts_comparisons=sum(m['counts_comparisons'] for c in cases for m in c['methods']),
              files={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='completed.json'})
    (output/'completed.json').write_text(json.dumps(done,indent=2),encoding='utf-8')
    print(f'Finished: {output / "report.md"}',flush=True)


if __name__=='__main__':main()
