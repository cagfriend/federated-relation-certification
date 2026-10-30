"""Read-only result audit; never reruns training or edits original results."""
import hashlib
import json
import statistics as st
from pathlib import Path

import numpy as np

from experiments.public_scaling.config import from_json
from experiments.public_scaling.data import sha, source_hashes, verify_prepared
from experiments.public_scaling.graphs import make_graph
from experiments.public_scaling.run import checked_case, checked_profile, check_shared_cases
from experiments.public_scaling.util import load_json

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RESULTS = ROOT / 'experiments/public_scaling/results_public'


def main():
    complete = load_json(RESULTS / 'completed.json')
    env = load_json(RESULTS / 'environment.json')
    assert complete['source_hashes'] == env['source_hashes'] == source_hashes()
    for name, digest in complete['file_hashes'].items():
        assert sha(RESULTS / name) == digest, name
    assert env['seeds'] == [404, 505, 606]
    assert (complete['case_count'], complete['method_runs'], complete['memory_profiles']) == (9, 27, 9)
    cases = []
    prepared_files = 0
    for seed in env['seeds']:
        marker = load_json(RESULTS / f'prepared_{seed}.json')
        directory = Path(marker['path'])
        assert sha(directory / 'prepared.json') == marker['metadata_sha256']
        metadata = load_json(directory / 'prepared.json')
        verify_prepared(directory, metadata)
        prepared_files += len(metadata['files'])
        public = np.load(directory / 'public_ids.npy')
        private = [np.load(directory / f'client_{i}_private_ids.npy') for i in range(6)]
        assert len(public) == 16384 and sum(map(len, private)) == 43616
        all_ids = np.concatenate([public] + private)
        assert len(np.unique(all_ids)) == 60000
        graphs = []
        for cfg in env['plan']:
            config = from_json(cfg)
            case = checked_case(RESULTS / f'{config.case_id}_seed_{seed}.json', config, seed, directory)
            graph = make_graph(config.samples, config.degree, seed)
            assert hashlib.sha256(graph.tobytes()).hexdigest() == case['graph_sha256']
            graphs.append(graph)
            by_method = {n: [r for r in case['round_records'] if r['method'] == n] for n in ('B', 'E', 'D')}
            for rnd in range(200):
                rows = [by_method[n][rnd] for n in ('B', 'E', 'D')]
                assert len({r['head_digest_after_public'] for r in rows}) == 1
                assert rows[0]['traffic'] == rows[1]['traffic'] == rows[2]['traffic']
                for k in ('private_loss', 'public_loss', 'student_forward_endpoints', 'private_optimizer_steps', 'public_optimizer_steps'):
                    assert rows[0][k] == rows[1][k] == rows[2][k], (seed, config.samples, rnd, k)
            metrics = {n: [{k: v for k, v in m.items() if k != 'method'} for m in case['metrics'] if m['method'] == n] for n in ('B', 'E', 'D')}
            assert metrics['B'] == metrics['E'] == metrics['D']
            assert [m['round'] for m in metrics['B']] == list(range(20, 201, 20))
            for n in by_method:
                s = case['summary'][n]
                for phase in ('private', 'public', 'generation', 'exchange'):
                    assert abs(sum(r[f'{phase}_seconds'] for r in by_method[n]) - s[f'{phase}_seconds']) < 1e-8
                assert abs(s['initialization_seconds'] + sum(r['pipeline_seconds'] for r in by_method[n]) - s['training_pipeline_seconds']) < 1e-8
                assert s['private_optimizer_steps'] == 68400
                assert s['public_optimizer_steps'] == config.samples // 4096 * 9600
            cases.append(case)
        for small, big in zip(graphs, graphs[1:]):
            assert {tuple(e) for e in small}.issubset({tuple(e) for e in big})
    check_shared_cases(cases)
    memory = []
    for file in sorted(RESULTS.glob('memory_m*.json')):
        p = load_json(file)
        c = next(c for c in cases if c['case_id'] == p['case_id'] and c['seed'] == p['seed'])
        checked_profile(p, from_json(c['config']), p['seed'], c['summary'][p['method']]['persistent_method_array_bytes'])
        memory.append(p)
    paired = load_json(RESULTS / 'paired_summary.json')
    summary = {}
    for m in (4096, 8192, 16384):
        group = sorted([c for c in cases if c['config']['samples'] == m], key=lambda c: c['seed'])
        comparisons = {}
        for ref in ('B', 'E'):
            comparisons[ref] = {}
            for field in ('generation_seconds', 'training_pipeline_seconds', 'with_shared_preparation_seconds'):
                ratios = [c['summary']['D'][field] / c['summary'][ref][field] for c in group]
                saved = [c['summary'][ref][field] - c['summary']['D'][field] for c in group]
                recorded = paired['paired'][f'm{m}_d1']['paired'][f'D_over_{ref}'][field]
                assert abs(st.median(ratios) - recorded['median_ratio_D_over_reference']) < 1e-12
                assert abs(st.median(saved) - recorded['median_seconds_saved']) < 1e-8
                comparisons[ref][field] = dict(percent_less=100 * (1 - st.median(ratios)), seconds_saved=st.median(saved), wins=sum(r < 1 for r in ratios), ratio_range=[min(ratios), max(ratios)])
        metrics = [cl for c in group for me in c['metrics'] if me['method'] == 'D' for cl in me['clients']]
        summary[str(m)] = dict(comparisons=comparisons,
            recompute_percent={n: [100 * c['summary'][n]['teacher_recompute_fraction_after_bootstrap'] for c in group] for n in ('E', 'D')},
            B_generation_share_percent=[100 * c['summary']['B']['generation_seconds'] / c['summary']['B']['training_pipeline_seconds'] for c in group],
            final_mean_acc=[c['summary']['D']['final_metrics']['mean']['acc'] for c in group],
            min_occupied_clusters_over_evaluations=min(cl['occupied_clusters'] for cl in metrics),
            max_largest_cluster_fraction_over_evaluations=max(cl['largest_cluster_fraction'] for cl in metrics),
            traffic_bytes=[c['summary']['D']['traffic']['total_bytes'] for c in group],
            D_persistent_mib=group[0]['summary']['D']['persistent_method_array_bytes']/2**20,
            D_extra_persistent_over_B_mib=(group[0]['summary']['D']['persistent_method_array_bytes']-group[0]['summary']['B']['persistent_method_array_bytes'])/2**20)
    report = dict(result_directory=str(RESULTS), verified_root_json_hashes=len(complete['file_hashes']), verified_prepared_files=prepared_files,
        verified_source_files=len(complete['source_hashes']), case_seed_count=len(cases), method_runs=27, memory_profiles=len(memory),
        exact_matching_paired_rounds=1800, matching_evaluation_triplets=90,
        relation_comparisons=sum(c['validation']['relation_comparisons'] for c in cases),
        candidate_membership_comparisons=sum(c['validation']['candidate_membership_comparisons'] for c in cases), mismatches=0,
        memory_mib={n: {k: st.median(p[k] for p in memory if p['method'] == n)/2**20 for k in ('persistent_method_array_bytes','tracemalloc_peak_bytes','process_peak_working_set_bytes')} for n in ('B','E','D')},
        summary=summary,
        limits=['Stored oracle checks inspected; training and full oracles not rerun.', 'Timings exclude oracle, evaluation and preparation; frozen-encoder head training only.', 'Three seeds; no inference of statistical significance.', 'Public M and matching edge count grow together; student SGD steps also grow.', 'Only largest M has process memory replay.'])
    (OUT / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
