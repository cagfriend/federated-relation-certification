"""Single-method execution and cross-run trajectory identity.

The training step itself is experiments.private_workload.engine.run with
names=(method,): every random stream in that engine is seeded by
(seed, client, round), never by process-global state, and joint runs
assert all methods follow one identical trajectory. A single-method
process therefore reproduces exactly its slice of the joint trajectory,
which check_block_identity verifies across methods and repeats using
only non-timing fields.
"""
import os
from experiments.private_workload.engine import run as _workload_run

# Round-record fields that must agree across B/E/D and across repeats.
TRAJECTORY_KEYS = (
    'head_digest_after_public', 'public_schedule_digest', 'public_optimizer_steps',
    'student_forward_endpoints', 'public_edges_consumed', 'committed_counts_digest',
    'received_counts_digests', 'private_loss', 'public_loss', 'private_subset_digest',
    'private_samples_per_client', 'private_subset_pseudo_histograms',
    'private_optimizer_steps', 'private_forward_endpoints',
    'positive_relation_fraction', 'traffic',
)
# Extra fields that must also agree between repeats of the same method.
METHOD_KEYS = ('teacher_forward_endpoints', 'certified_edges_before_refresh',
               'client_statistics', 'persistent_method_array_bytes')
TIMING_KEYS = ('private_seconds', 'generation_seconds', 'exchange_seconds',
               'public_seconds', 'pipeline_seconds')


def run_single(directory, spec, method, *, fixture=False):
    """Run one method in this process; return a single-run record."""
    result = _workload_run(directory, spec, names=(method,), fixture=fixture)
    summary = result['summary'][method]
    return dict(
        seed=result['seed'], dataset=result['dataset'], config=result['config'],
        spec=result['spec'], case_id=result['case_id'], method=method,
        initial_head_digest=result['initial_head_digest'],
        graph_sha256=result['graph_sha256'],
        prepared_directory=result['prepared_directory'],
        common_preparation_seconds=result['common_preparation_seconds'],
        shared_loading_seconds=result['shared_loading_seconds'],
        summary={method: summary},
        round_records=[r for r in result['round_records'] if r['method'] == method],
        metrics=[q for q in result['metrics'] if q['method'] == method],
        coverage=result['coverage'], coverage_records=result['coverage_records'],
        validation=result['validation'],
        process=dict(pid=os.getpid()),
    )


def _strip(row, keys):
    return {k: row[k] for k in keys}


def trajectory_signature(run):
    """Everything that must be identical for same (partition, seed, tier)."""
    rounds = {}
    for row in run['round_records']:
        rounds[row['round']] = _strip(row, TRAJECTORY_KEYS)
    metrics = [{k: v for k, v in q.items() if k != 'method'} for q in run['metrics']]
    summary = run['summary'][run['method']]
    return dict(rounds=rounds, metrics=metrics,
                coverage_records=run['coverage_records'], coverage=run['coverage'],
                initial_head_digest=run['initial_head_digest'],
                graph_sha256=run['graph_sha256'],
                final_head_digest=summary['final_head_digest'],
                final_metrics={k: v for k, v in (summary['final_metrics'] or {}).items() if k != 'method'},
                traffic_total=summary['traffic'],
                public_optimizer_steps=summary['public_optimizer_steps'],
                student_forward_endpoints=summary['student_forward_endpoints'],
                private_optimizer_steps=summary['private_optimizer_steps'],
                private_forward_endpoints=summary['private_forward_endpoints'],
                # Candidate-membership counts are method-specific by design
                # (B audits no candidate sets); they are checked per method
                # in method_signature instead.
                relation_comparisons=run['validation']['relation_comparisons'])


def method_signature(run):
    """Trajectory plus method-specific counters; repeats must match fully."""
    sig = trajectory_signature(run)
    sig['method_rounds'] = {row['round']: _strip(row, METHOD_KEYS) for row in run['round_records']}
    sig['candidate_membership_comparisons'] = run['validation']['candidate_membership_comparisons']
    return sig


def check_block_identity(runs):
    """runs: the 6 records of one (partition, seed, tier). Raises on drift."""
    if len(runs) != 6:
        raise ValueError('A block needs 3 methods x 2 repeats')
    sigs = [trajectory_signature(r) for r in runs]
    for sig in sigs[1:]:
        if sig != sigs[0]:
            raise AssertionError('Trajectory differs across methods/repeats')
    by_method = {}
    for r in runs:
        by_method.setdefault(r['method'], []).append(r)
    for method, group in by_method.items():
        if len(group) != 2:
            raise ValueError('Each method needs exactly 2 repeats')
        if method_signature(group[0]) != method_signature(group[1]):
            raise AssertionError(f'Repeat drift for method {method}')
    return dict(blocks_checked=1, runs_compared=len(runs), mismatches=0)
