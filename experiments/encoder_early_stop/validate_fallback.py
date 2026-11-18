"""Targeted multi-client rollback on the two observed failure cases."""
import argparse
from pathlib import Path
from statistics import mean
from time import perf_counter

from threadpoolctl import threadpool_limits
import torch

from .validate_selection import ROUNDS, SHARED, measure, run_arm, screen, select, snapshots
from experiments.external_pilot.common import batches, model_digest
from experiments.external_pilot.design import config
from experiments.external_pilot.prepare import load, read, sha, write
from experiments.private_corrected_guard.run import seal_result, verify_seal
from experiments.public_scaling.certification import make_matching


CASES = ((1207, 'dirichlet_0.1'), (1208, 'iid'))
MAX_SHARE = .50
ACC_MARGIN = .01
PREVIOUS = SHARED / 'results_selection_validation'


def acceptable(s):
    return s['eligible'] and max(s['private_largest'], s['public_largest']) <= MAX_SHARE


def choose(probes):
    """Prefer candidates meeting the concentration screen, then select by pair count."""
    safe = {step: probe for step, probe in probes.items() if acceptable(probe)}
    if safe:
        return select(safe), 'within_concentration_limit'
    step = select(probes)
    return (step, 'concentrated_fallback' if step is not None else 'no_nonempty_candidate')


def audit_previous(seed, partition):
    label = f'{seed}_{partition}_c1'
    completed = read(PREVIOUS / 'completed.json')
    item = next(r for r in completed['validation'] if (r['seed'], r['partition']) == (seed, partition))
    path = PREVIOUS / 'decisions' / f'{label}.json'
    if sha(path) != item['decision_sha256']:
        raise ValueError('Previous decision receipt failed')
    old_step = item['selected']
    arm = item['arms'][str(old_step)]
    old = None
    if arm['status'] == 'completed':
        path = PREVIOUS / 'runs' / f'{label}_step{old_step}.json'
        verify_seal(path)
        if sha(path) != arm['sha256']:
            raise ValueError('Previous run receipt failed')
        old = read(path)
    return item, old


def per_client(result):
    last = result['checkpoints'][-1]['clients']
    tail = result['checkpoints'][-4:]
    return [dict(client=c,
                 teacher_tail=mean(r['teacher_rates'][c] for r in result['rows'][-40:]),
                 test_largest_tail=mean(q['clients'][c]['largest'] for q in tail),
                 acc=s['acc'], nmi=s['nmi'], ari=s['ari'], test_occupied=s['occupied'])
            for c, s in enumerate(last)]


def compare(reference, candidate):
    ref, new = reference['clients'], candidate['clients']
    acc_deltas = [y['acc'] - x['acc'] for x, y in zip(ref, new)]
    return dict(network_mean_acc_delta=mean(acc_deltas),
                worst_acc_delta=min(y['acc'] for y in new) - min(x['acc'] for x in ref),
                min_client_acc_delta=min(acc_deltas),
                client_acc_guard=min(acc_deltas) >= -ACC_MARGIN - 1e-12,
                worst_tail_largest_delta=max(y['test_largest_tail'] for y in new)
                - max(x['test_largest_tail'] for x in ref))


def execute(out, seed, partition):
    cfg = dict(config('pilot'), seed=seed)
    label = f'{seed}_{partition}'
    cache = PREVIOUS / 'cache' / str(seed)
    old, historical = audit_previous(seed, partition)
    models, train, meta = load(cache, partition, cfg)
    if old['cache_files'] != meta['files']:
        raise ValueError('Cache differs from the previous run')
    edges = make_matching(len(train['public']), seed)
    candidate_models, probes, last_steps, picked, warnings = [], [], [], [], []
    timing = []
    for c, cached in enumerate(models):
        x = train['private'][c]
        last = sum(len(batches(len(x), cfg['local_batch'], seed + 101*c + epoch))
                   for epoch in range(cfg['ae_epochs']))
        last_steps.append(last)
        start = perf_counter()
        terminal = screen(cfg, c, cached, train, edges)
        terminal_seconds = perf_counter() - start
        states, scores = {last: cached}, {last: terminal}
        replay_seconds = extra_screen_seconds = 0.
        if not acceptable(terminal) or (c == 1 and old['selected'] != last):
            earlier_steps = range(1, last) if not acceptable(terminal) else (old['selected'],)
            start = perf_counter()
            states.update(snapshots(cfg, c, x, cached, earlier_steps))
            replay_seconds = perf_counter() - start
            start = perf_counter()
            scores.update({s: screen(cfg, c, states[s], train, edges) for s in earlier_steps})
            extra_screen_seconds = perf_counter() - start
        if acceptable(terminal):
            chosen, status = last, 'terminal_within_limit'
        else:
            chosen, status = choose(scores)
        picked.append(chosen)
        warnings.append(status)
        candidate_models.append(states)
        probes.append(scores)
        timing.append(dict(client=c, terminal_screen_seconds=terminal_seconds,
                           replay_with_copy_seconds=replay_seconds, earlier_screen_seconds=extra_screen_seconds))

    for c, terminal in enumerate(last_steps):
        if c != 1 and probes[c][terminal] != old['shared_clients'][str(c)]:
            raise ValueError(f'Terminal screening differs for unchanged client {c}')
    if probes[1][old['selected']] != old['screening'][str(old['selected'])]:
        raise ValueError('Cannot reproduce previous selection screening')
    previous = last_steps.copy()
    previous[1] = old['selected']
    plan = {'previous': previous, 'all_client_fallback': picked}
    if seed == 1207:
        recovered = previous.copy()
        recovered[2] = picked[2]
        plan['client2_only_recovery'] = recovered
    decision = dict(seed=seed, partition=partition, terminal_steps=last_steps, plan=plan,
                    client_status=warnings, screening=probes, timings=timing,
                    cache_files=meta['files'], previous_decision_sha256=old['decision_sha256'])
    decision_path = out / 'decisions' / f'{label}.json'
    write(decision_path, decision)

    test = torch.load(cache / partition / 'evaluation.pt', weights_only=True)
    arms = {}
    for name, steps in plan.items():
        blocked = [c for c, s in enumerate(steps) if s is None or not probes[c][s]['eligible']]
        if blocked:
            arms[name] = dict(status='blocked', clients=blocked)
            print(f'{label} {name}: blocked by {blocked}', flush=True)
            continue
        chosen_models = [states[s] for states, s in zip(candidate_models, steps)]
        checked = {c: probes[c][s] for c, s in enumerate(steps)}
        result = run_arm(cfg, 1, chosen_models, train, test, checked)
        if name == 'previous' and historical is not None:
            steps_match = ([r['head_digest'] for r in result['rows']] == [r['head_digest'] for r in historical['rows']]
                           and result['checkpoints'] == historical['checkpoints'])
            if not steps_match:
                raise ValueError('Previous arm does not reproduce its saved trajectory')
        if result['encoder_hashes'] != [model_digest([m]) for m in chosen_models]:
            raise ValueError('Arm did not use its assigned snapshots')
        result_path = out / 'runs' / f'{label}_{name}.json'
        write(result_path, result)
        seal_result(result_path)
        arms[name] = dict(status='completed', sha256=sha(result_path), clients=per_client(result),
                          summary=measure(result, 1), relation_audits=result['relation_audits'],
                          historical_replay=name == 'previous' and historical is not None)
        print(f'{label} {name}: completed 200 rounds', flush=True)
    ref = 'client2_only_recovery' if seed == 1207 else 'previous'
    paired = None
    if arms[ref]['status'] == arms['all_client_fallback']['status'] == 'completed':
        paired = compare(arms[ref], arms['all_client_fallback'])
    return dict(**decision, decision_sha256=sha(decision_path), arms=arms, comparison_reference=ref, comparison=paired)


def report(out, cases):
    lines = ['# STL-10 multi-client encoder fallback', '',
             'Teacher rates use rounds 161–200. Test largest cluster uses checkpoints 170/180/190/200.', '',
             '| Seed | Partition | Arm | Encoders | Status | Client 1 teacher | Client 1 test largest | Worst test largest | Mean ACC |',
             '|---|---|---|---|---|---:|---:|---:|---:|']
    for item in cases:
        for name, arm in item['arms'].items():
            numbers = ['—'] * 4
            if arm['status'] == 'completed':
                c1 = arm['clients'][1]
                numbers = [f"{v:.2%}" for v in (c1['teacher_tail'], c1['test_largest_tail'],
                           max(c['test_largest_tail'] for c in arm['clients']), arm['summary']['network_acc'])]
            lines.append(f"| {item['seed']} | {item['partition']} | {name} | {item['plan'][name]} |"
                         f" {arm['status']} | {' | '.join(numbers)} |")
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=SHARED / 'results_fallback_validation')
    args = parser.parse_args()
    out = args.output.resolve()
    if out.is_relative_to(PREVIOUS) or PREVIOUS.is_relative_to(out):
        parser.error('Output overlaps previous experiment')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error('Output must be a new or empty directory')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    write(out/'design.json', dict(cases=CASES, rounds=ROUNDS, concentration_limit=MAX_SHARE, acc_margin=ACC_MARGIN,
                                 candidates='All completed AE updates for clients whose terminal snapshot fails screening.',
                                 rank='Prefer nonempty candidates within both maximum-cluster limits; minimize public pair numerator; later on ties.',
                                 script_sha256=sha(Path(__file__)), prior_completed_sha256=sha(PREVIOUS/'completed.json')))
    with threadpool_limits(1):
        results = [execute(out, seed, part) for seed, part in CASES]
    report(out, results)
    write(out/'completed.json', dict(cases=results, design_sha256=sha(out/'design.json'),
                                     report_sha256=sha(out/'report.md')))


if __name__ == '__main__':
    main()
