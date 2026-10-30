"""Run the frozen M=4096, degree=1/4/8 experiment using the existing core."""
import argparse
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from experiments.public_scaling.config import make_plan, preset
from experiments.public_scaling.data import sha
from experiments.public_scaling.run import checked_case, validate_environment
from experiments.public_scaling.util import load_json
from .analyze import analyze


ROOT = Path(__file__).resolve().parents[2]


def preflight(reference, output):
    reference, output = Path(reference).resolve(), Path(output).resolve()
    if output == reference or reference in output.parents or output in reference.parents:
        raise ValueError('Use a separate output directory outside the reference directory')
    env = load_json(reference / 'environment.json')
    validate_environment(env)
    done = load_json(reference / 'completed.json')
    if done['source_hashes'] != env['source_hashes'] or done['mismatches'] != 0:
        raise ValueError('Invalid reference completion')
    for name, digest in done['file_hashes'].items():
        if Path(name).name != name or sha(reference / name) != digest:
            raise ValueError(f'Reference file changed: {name}')
    plan = make_plan(replace(preset('full'), prepare_device='cuda'), 'graph')
    if env['seeds'] != [404, 505, 606] or env['preset'] != 'full':
        raise ValueError('This frozen follow-up requires the completed full 404/505/606 experiment')
    for seed in env['seeds']:
        marker = load_json(reference / f'prepared_{seed}.json')
        directory = Path(marker['path'])
        if sha(directory / 'prepared.json') != marker['metadata_sha256']:
            raise ValueError('Prepared manifest changed')
        checked_case(reference / f'm4096_d1_seed_{seed}.json', plan[0], seed, directory)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=ROOT / 'experiments/public_scaling/results_public')
    parser.add_argument('--output', type=Path, default=ROOT / 'experiments/graph_density/results_graph')
    parser.add_argument('--memory-scope', choices=('largest', 'all'), default='largest')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--check-only', action='store_true', help='Validate reuse and print design; no training or output writes')
    args = parser.parse_args()
    # Resolve user paths before setting the child working directory.
    reference, output = args.reference.resolve(), args.output.resolve()
    plan = preflight(reference, output)
    if output.exists() and any(output.iterdir()) and not args.resume:
        raise FileExistsError('Output is nonempty; use --resume or a new directory')
    if args.resume:
        env = load_json(output / 'environment.json')
        if (env['plan'] != [c.json() for c in plan] or env['seeds'] != [404, 505, 606]
                or env['reuse_from'] != str(reference) or not env['memory_audit']):
            raise ValueError('Resume output does not match the frozen graph experiment')
        scope = env['memory_scope']
    else:
        scope = args.memory_scope
    print('Frozen graph experiment: M=4096, K=10, rounds=200, seeds=404/505/606', flush=True)
    for c in plan:
        edges = c.samples * c.degree // 2
        print(f'{c.case_id}: edges={edges}, public steps/client/round={(edges + 255)//256}', flush=True)
    print(f'Reuse 3 degree=1 cases; new training: 18 method runs; isolated memory replays: {9 if scope == "largest" else 27}', flush=True)
    if args.check_only:
        return
    cmd = [sys.executable, '-m', 'experiments.public_scaling.run', '--output', str(output)]
    if args.resume:
        cmd += ['--resume']
    else:
        reference_env = load_json(reference / 'environment.json')
        cmd += ['--preset', 'full', '--suite', 'graph', '--prepare-device', 'cuda',
                '--reuse-from', str(reference), '--memory-audit', '--memory-scope', scope,
                '--cache', reference_env['cache'], '--data-dir', reference_env['data_dir']]
    subprocess.run(cmd, cwd=ROOT, check=True)
    analyze(output)
    print(f'Graph diagnostics: {output / "graph_analysis/report.md"}', flush=True)


if __name__ == '__main__':
    main()
