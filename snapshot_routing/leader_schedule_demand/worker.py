"""Use the historical timing windows and verify the changed byte identity."""

from unittest.mock import patch

from experiments.snapshot_certification_timing.design import require
from ..shared_schedule_demand import worker as previous
from .protocol import LeaderScheduleProtocol

EXPLICIT = previous.EXPLICIT
LEADER = 'LeaderDemand'
METHODS = ('D', EXPLICIT, LEADER)


def run(source, ref, base, prep, bank, method, baseline, *, audit):
    args = (source, ref, base, prep, bank)
    if method == LEADER:
        with patch.object(previous, 'SharedScheduleProtocol', LeaderScheduleProtocol):
            return previous.run(*args, previous.SHARED, baseline, audit=audit)
    require(method in METHODS, 'Unknown experiment path')
    return previous.run(*args, method, baseline, audit=audit)


def leader_accounting(explicit, leader):
    old, new = explicit['traffic_breakdown'], leader['traffic_breakdown']
    request = old['request_up_bytes']
    require(request > 0 and old['union_down_bytes'] > 0
            and {key: value for key, value in old.items() if key != 'request_up_bytes'} == new,
            'Leader reconstruction changed the union broadcast or other round payloads')
    base, setup = explicit['setup_traffic'], leader['setup_traffic']
    extra_up = setup['up_bytes']-base['up_bytes']
    extra_down = setup['down_bytes']-base['down_bytes']
    extra_messages = setup['messages']-base['messages']
    require(extra_up > 0 and extra_down > 0 and extra_messages == base['messages'] and extra_messages % 2 == 0,
            'Schedule registration or acknowledgements missing')

    a, b = explicit['traffic'], leader['traffic']
    net_up, net_down = request-extra_up, -extra_down
    require(a['up_bytes']-b['up_bytes'] == net_up and a['down_bytes']-b['down_bytes'] == net_down
            and a['total_bytes']-b['total_bytes'] == net_up+net_down, 'Traffic accounts do not balance')
    removed_messages = extra_messages//2 * len(explicit['scope'])
    require(a['messages']-b['messages'] == removed_messages-extra_messages, 'Message count does not balance')
    return dict(request_up_removed=request, union_down_retained=new['union_down_bytes'],
                schedule_setup_up=extra_up, schedule_setup_down=extra_down,
                net_up_saved=net_up, net_down_saved=net_down, net_total_saved=net_up+net_down,
                request_messages_removed=removed_messages, schedule_setup_messages=extra_messages,
                net_messages_saved=removed_messages-extra_messages)
