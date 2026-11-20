"""Recheck one stored graph-scaling B/E/D timing block without editing the original."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from experiments.snapshot_graph_scaling.run import (
    PACKAGE, ROOT, configs, context_id, environment, history_pair, pair, read, require,
    run, run_path, seal, sealed, sha, sources, verify,
)
from experiments.snapshot_graph_scaling.inputs import verify_bank
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.report import metrics
import torch
from threadpoolctl import threadpool_limits


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--block', required=True, help='cell:repeat, e.g. 1207_dirichlet_0.1_m16384:1')
    cli.add_argument('--original', type=Path, default=PACKAGE/'results_full')
    cli.add_argument('--output', type=Path)
    cli.add_argument('--resume', action='store_true')
    cli.add_argument('--worker', choices=('B', 'E', 'D'), help=argparse.SUPPRESS)
    args = cli.parse_args()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(args)


def execute(args):
    original = args.original.resolve()
    mp = original/'manifest.json'
    manifest, identity = read(mp), sha(mp)
    require(environment() == manifest['environment'] and sources() == manifest['source_hashes'] and
            sha(PACKAGE/'README.md') == manifest['design_sha256'], 'Original environment, source or design has changed')
    cases = [c for c in manifest['schedule'] if c['stage'] == 'timing' and
             f"{cell_id(c)}:{c['repeat']}" == args.block]
    require(len(cases) == 3 and {c['method'] for c in cases} == set('BED'), 'Unknown timing block')
    out = (args.output or ROOT/'outputs'/'snapshot_graph_retests'/args.block.replace(':', '_r')).resolve()
    history, ref, cache = (Path(manifest[k]).resolve() for k in ('history_root', 'reference_root', 'cache'))
    protected = [original, history, ref, cache]
    if manifest['raw_file']:
        protected.append(Path(manifest['raw_file']).resolve().parent)
    require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in protected), 'Retest output overlaps input')
    audit, done, banks = (sealed(original/p) for p in ('audit_passed.json', 'completed.json', 'banks_sealed.json'))
    require(all(r['manifest_sha256'] == identity for r in (audit, done, banks)) and
            done['audit_sha256'] == sha(original/'audit_passed.json'), 'Original completion or audit receipt changed')
    memo_path = out/'request.json'
    memo = dict(original=str(original), source_manifest_sha256=identity, block=args.block, schedule=cases,
                script_sha256=sha(Path(__file__)))
    if memo_path.exists():
        require((args.resume or args.worker) and sealed(memo_path) == memo, 'Use --resume with the same retest inputs')
    else:
        require(not args.worker and (not out.exists() or not any(out.iterdir())), 'Retest output must be new')
        seal(memo_path, memo)
    prep_dir = ref/'preparation'
    c0 = cases[0]
    cid = context_id(c0)
    base, cfg = configs(manifest['preset'], c0)
    old, anchors = history_pair(history, base, c0['partition'])
    prep_path = prep_dir/f'{cid}.json'
    require(anchors == manifest['history'][cid] and sha(prep_path) == manifest['preparation'][cid] and
            sha(ref/'manifest.json') == manifest['reference_manifest'], 'Original snapshot inputs changed')
    bp = original/'banks'/f"{c0['seed']}.json"
    require(sha(bp) == banks['banks'][str(c0['seed'])], 'Original public bank receipt changed')
    bank = verify_bank(bp) if not args.worker else sealed(bp)

    def source_case(c):
        ac = dict(c, stage='audit', repeat=1)
        for case, receipt in ((c, done), (ac, audit)):
            path = run_path(case)
            require(sha(original/path) == receipt['hashes'][path], f'Original run changed: {path}')
        a = verify(original/run_path(ac), ac, manifest['preset'], identity)
        b = verify(original/run_path(c), c, manifest['preset'], identity)
        pair(a, b)
        return a, b

    if args.worker:
        c = next(c for c in cases if c['method'] == args.worker)
        a, _ = source_case(c)
        r = run(original, c, base, cfg, prep_dir, cache/str(c['seed']), old, anchors, bank)
        seal(out/run_path(c), dict(manifest_sha256=identity, retest_request=sha(memo_path), **r))
        return

    prep = sealed(prep_path)
    results = []
    for c in cases:
        dest = out/run_path(c)
        a, b = source_case(c)
        if not dest.with_suffix('.sha256.json').exists():
            print(f"Retesting {args.block} / {c['method']}", flush=True)
            cmd = [sys.executable, '-B', str(Path(__file__).resolve()), '--block', args.block,
                   '--original', str(original), '--output', str(out), '--worker', c['method']]
            subprocess.run(cmd, cwd=ROOT, check=True)
        r = verify(dest, c, manifest['preset'], identity)
        require(r['retest_request'] == sha(memo_path), 'Retest receipt belongs to another request')
        pair(a, r)
        results.append(dict(method=c['method'], original=metrics(b, prep), retest=metrics(r, prep)))
    seal(out/'comparison.json', dict(request=memo, results=results,
                                    hashes={run_path(c): sha(out/run_path(c)) for c in cases}))
    print(f"Finished: {out/'comparison.json'}", flush=True)
    for r in results:
        b, d = r['original'], r['retest']
        print(f"{r['method']}: head {b['head_seconds']:.4f}s -> {d['head_seconds']:.4f}s, "
              f"generation {b['generation_seconds']:.4f}s -> {d['generation_seconds']:.4f}s, "
              f"AC checks {d['ac_samples']}, battery checks {d['battery_samples']}")


if __name__ == '__main__':
    main()
