"""Replay real SGD snapshots to test E/D choice with independent continuous caches."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
from time import perf_counter

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.public_scaling.certification import hard_relations
from experiments.public_scaling.config import from_json
from experiments.public_scaling.data import Prepared, sha, json_write_new
from experiments.public_scaling.engine import Method, evaluate
from experiments.public_scaling.protocol import RelationProtocol
from experiments.public_scaling.run import checked_case, validate_environment, verify_marker
from experiments.public_scaling.util import load_json, seal_payload, validate_payload
from .selection import POLICIES, RULE, PolicyGenerator, choose

ROOT = Path(__file__).resolve().parents[2]


def sources():
    return {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}


def cache_digest(generator):
    h = hashlib.sha256(str(generator.round).encode())
    for key in sorted(generator.persistent_arrays()):
        array = getattr(generator, key)
        h.update(key.encode()); h.update(str((array.shape, array.dtype.str)).encode())
        h.update(array.tobytes())
    return h.hexdigest()


def replay(directory, config, reference, *, fixture=False):
    data = Prepared(directory, config, allow_test_fixture=fixture)
    try:
        trainer = Method('E', data, config)
        historical = {(r['round'], r['method']): r for r in reference['round_records']}
        generators = {p: [] for p in POLICIES}
        protocols, initialization = {}, {}
        for p in POLICIES:
            t = perf_counter()
            protocols[p] = RelationProtocol(data.edges, config.samples, config.classes,
                                            config.dimensions, adaptive=True)
            initialization[p] = perf_counter() - t
        rows, exchanges, quality, training = [], [], [], []
        relations_checked, membership_checked = 0, 0
        for rnd in range(1, config.rounds + 1):
            trained, _, snapshots = trainer.step(rnd)
            old = historical[(rnd, 'E')]
            if (trained['head_digest_after_public'] != old['head_digest_after_public']
                    or trained['traffic'] != old['traffic']):
                raise AssertionError('Shared training diverged from historical E')
            training.append(dict(round=rnd, head_digest=trained['head_digest_after_public'],
                                 traffic=trained['traffic']))
            relations = {p: [] for p in POLICIES}
            for client, (w, b) in enumerate(snapshots):
                labels = (data.public[client] @ w.T + b).argmax(axis=1)
                oracle = hard_relations(labels, data.edges)
                shift = (data.seed + rnd + client) % len(POLICIES)
                order = POLICIES[shift:] + POLICIES[:shift]
                for policy in order:
                    t = perf_counter()
                    # Own snapshot copy cost for every path, included in timer.
                    ww, bb = w.copy(), b.copy()
                    if rnd == 1:
                        g = PolicyGenerator(data.public[client], ww, bb, data.edges,
                                            policy, config.degree)
                        generators[policy].append(g)
                        relation = g.initial_relations
                        del g.initial_relations
                        stats = dict(forward_endpoints=config.samples,
                                     candidate_entries=config.samples * config.classes,
                                     certified_edges_before_refresh=0, selected_path='bootstrap',
                                     previous_refresh_fraction=None, switched=False, decision_seconds=0.0)
                    else:
                        g = generators[policy][client]
                        relation, stats = g.generate(ww, bb)
                    seconds = perf_counter() - t
                    if not np.array_equal(relation, oracle):
                        raise AssertionError(f'{policy}: relation differs from full oracle')
                    if not np.all(g.candidate_matrix()[np.arange(config.samples), labels]):
                        raise AssertionError('Current winning class excluded from cache candidates')
                    if policy in ('E', 'D'):
                        expected = historical[(rnd, policy)]['client_statistics'][client]
                        if any(stats[k] != expected[k] for k in
                               ('forward_endpoints', 'candidate_entries', 'certified_edges_before_refresh')):
                            raise AssertionError('Fixed-policy cache differs from historical method')
                    relations_checked += len(oracle)
                    membership_checked += config.samples
                    relations[policy].append(relation)
                    rows.append(dict(round=rnd, client=client, width=config.dimensions[client],
                                     policy=policy, bootstrap=rnd == 1, generation_seconds=seconds,
                                     statistics=stats, cache_digest=cache_digest(g),
                                     persistent_cache_bytes=sum(g.persistent_arrays().values())))
            counts = np.sum(relations['E'], axis=0, dtype=np.int64)
            shift = (data.seed + rnd) % len(POLICIES)
            for policy in POLICIES[shift:] + POLICIES[:shift]:
                protocol = protocols[policy]
                t = perf_counter(); traffic = protocol.exchange(relations[policy])
                exchange_s = perf_counter() - t
                if traffic != old['traffic'] or not np.array_equal(protocol.counts, counts):
                    raise AssertionError('Traffic or aggregate targets differ from historical E')
                if any(not np.array_equal(c, counts) for c in protocol.client_counts):
                    raise AssertionError('Incorrect client target')
                if any(not np.array_equal(a, b) for a, b in
                       zip(protocol.server_relations, relations[policy])):
                    raise AssertionError('Incorrect decoded relation')
                exchanges.append(dict(round=rnd, policy=policy, exchange_seconds=exchange_s,
                                      traffic=traffic,
                                      counts_digest=hashlib.sha256(counts.tobytes()).hexdigest()))
            if rnd % config.eval_every == 0 or rnd == config.rounds:
                metric = dict(method='E', round=rnd, **evaluate(trainer.heads, data, config))
                if metric != next(m for m in reference['metrics'] if m['method'] == 'E' and m['round'] == rnd):
                    raise AssertionError('Evaluation differs from historical E')
                quality.append(metric)
            if rnd % 10 == 0 or rnd == config.rounds:
                print(f'{config.case_id} seed={data.seed}: {rnd}/{config.rounds}', flush=True)
        return dict(case_id=config.case_id, seed=data.seed, config=config.json(),
                    records=rows, exchanges=exchanges, training=training, quality=quality,
                    protocol_initialization_seconds=initialization,
                    relation_comparisons=relations_checked, candidate_membership_comparisons=membership_checked,
                    mismatches=0)
    finally:
        data.close()


def check_case(case, config, seed, identity, reference):
    validate_payload(case)
    expected = {(r, c, p) for r in range(1, config.rounds + 1)
                for c in range(len(config.dimensions)) for p in POLICIES}
    actual = [(r['round'], r['client'], r['policy']) for r in case['records']]
    if (case['identity'] != identity or case['config'] != config.json() or case['seed'] != seed
            or case['case_id'] != config.case_id or case['mismatches'] != 0
            or len(actual) != len(expected) or set(actual) != expected):
        raise ValueError('Case identity or coverage mismatch')
    n = len(config.dimensions)
    if (case['relation_comparisons'] != len(POLICIES)*config.rounds*n*config.samples*config.degree//2
            or case['candidate_membership_comparisons'] != len(POLICIES)*config.rounds*n*config.samples):
        raise ValueError('Incorrect validation coverage')
    history = {(r['round'], r['method']): r for r in reference['round_records']}
    previous, paths = {}, {}
    for row in sorted(case['records'], key=lambda r: (r['round'], r['client'], r['policy'])):
        r, c, p = row['round'], row['client'], row['policy']
        stats = row['statistics']; key = (c, p)
        if (row['width'] != config.dimensions[c] or row['bootstrap'] != (r == 1)
                or not math.isfinite(row['generation_seconds']) or row['generation_seconds'] < 0
                or not math.isfinite(stats['decision_seconds']) or stats['decision_seconds'] < 0
                or stats['decision_seconds'] > row['generation_seconds']
                or len(row['cache_digest']) != 64 or row['persistent_cache_bytes'] <= 0
                or not 0 <= stats['forward_endpoints'] <= config.samples):
            raise ValueError('Invalid record')
        if r == 1:
            if (stats['selected_path'] != 'bootstrap' or stats['previous_refresh_fraction'] is not None
                    or stats['switched'] or stats['forward_endpoints'] != config.samples):
                raise ValueError('Incorrect bootstrap')
        else:
            last = previous.get(key)
            path = choose(p, config.degree, config.dimensions[c], last)
            if (stats['previous_refresh_fraction'] != last or stats['selected_path'] != path
                    or stats['switched'] != (key in paths and paths[key] != path)):
                raise ValueError('Noncausal or changed selection rule')
            paths[key] = path
            previous[key] = stats['forward_endpoints']/config.samples
        if p in ('E', 'D'):
            old = history[(r, p)]['client_statistics'][c]
            if any(stats[k] != old[k] for k in ('forward_endpoints', 'candidate_entries', 'certified_edges_before_refresh')):
                raise ValueError('Fixed-policy refresh mismatch')
    exchange_keys = [(r['round'], r['policy']) for r in case['exchanges']]
    expected_exchanges = {(r, p) for r in range(1, config.rounds+1) for p in POLICIES}
    if len(exchange_keys) != len(expected_exchanges) or set(exchange_keys) != expected_exchanges:
        raise ValueError('Incomplete exchange coverage')
    for row in case['exchanges']:
        if (not math.isfinite(row['exchange_seconds']) or row['exchange_seconds'] < 0
                or row['traffic'] != history[(row['round'], 'E')]['traffic']):
            raise ValueError('Invalid protocol record')
    for rnd in range(1, config.rounds+1):
        digests = {r['counts_digest'] for r in case['exchanges'] if r['round'] == rnd}
        if len(digests) != 1 or any(len(h) != 64 for h in digests):
            raise ValueError('Target digest mismatch')
    expected_training = [dict(round=r, head_digest=history[(r, 'E')]['head_digest_after_public'],
                              traffic=history[(r, 'E')]['traffic']) for r in range(1,config.rounds+1)]
    if case['training'] != expected_training or case['quality'] != [m for m in reference['metrics'] if m['method']=='E']:
        raise ValueError('Historical training or quality mismatch')
    if set(case['protocol_initialization_seconds']) != set(POLICIES) or any(
            not math.isfinite(t) or t < 0 for t in case['protocol_initialization_seconds'].values()):
        raise ValueError('Invalid protocol initialization')


def report(output, cases):
    rows = []
    for case in cases:
        for policy in POLICIES:
            records = [r for r in case['records'] if r['policy']==policy]
            post = [r for r in records if not r['bootstrap']]
            generation = sum(r['generation_seconds'] for r in records)
            exchange = sum(r['exchange_seconds'] for r in case['exchanges'] if r['policy']==policy)
            initialization = case['protocol_initialization_seconds'][policy]
            rows.append(dict(case_id=case['case_id'], seed=case['seed'], policy=policy,
                generation_with_bootstrap_seconds=generation,
                generation_after_bootstrap_seconds=sum(r['generation_seconds'] for r in post),
                generation_exchange_setup_seconds=generation+exchange+initialization,
                exchange_seconds=exchange, protocol_initialization_seconds=initialization,
                decision_seconds=sum(r['statistics']['decision_seconds'] for r in post),
                D_round_clients=sum(r['statistics']['selected_path']=='D' for r in post),
                E_round_clients=sum(r['statistics']['selected_path']=='E' for r in post),
                switches=sum(r['statistics']['switched'] for r in post),
                teacher_refresh_fraction=None if not post else sum(r['statistics']['forward_endpoints'] for r in post)
                    /(len(post)*case['config']['samples']),
                persistent_cache_bytes=sum(r['persistent_cache_bytes'] for r in records if r['bootstrap'])))
    fields=list(rows[0])
    with (output/'summary.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    paired=[]
    for case_id in sorted({r['case_id'] for r in rows}):
        for policy in ('D','static','adaptive'):
            for baseline in ('E','D','static'):
                if policy==baseline: continue
                for metric in ('generation_with_bootstrap_seconds','generation_after_bootstrap_seconds','generation_exchange_setup_seconds'):
                    values=[]; saved=[]
                    for seed in sorted({r['seed'] for r in rows if r['case_id']==case_id}):
                        a=next(r for r in rows if (r['case_id'],r['seed'],r['policy'])==(case_id,seed,policy))
                        b=next(r for r in rows if (r['case_id'],r['seed'],r['policy'])==(case_id,seed,baseline))
                        values.append(a[metric]/b[metric]); saved.append(b[metric]-a[metric])
                    paired.append(dict(case_id=case_id,policy=policy,baseline=baseline,metric=metric,
                        median_ratio=statistics.median(values),median_saved_seconds=statistics.median(saved),
                        wins=sum(v<1 for v in values),seeds=len(values)))
    (output/'summary.json').write_text(json.dumps(dict(rows=rows,paired=paired),indent=2),encoding='utf-8')
    text=['# E/D 路径选择可行性实验','',f'已保存 {len(cases)}/9 个配置-seed；completed.json 存在并校验通过才算完整。','',
          '主指标：包含首轮缓存初始化、快照复制和策略开销的关系生成时间。配对比值先逐 seed 计算再取中位数。', '',
          '|配置|策略|对照|含初始化生成耗时比|节省秒|胜出seed|','|---|---|---|---:|---:|---:|']
    for r in paired:
        if r['metric']=='generation_with_bootstrap_seconds':
            text.append(f"|{r['case_id']}|{r['policy']}|{r['baseline']}|{r['median_ratio']:.5f}|{r['median_saved_seconds']:.6f}|{r['wins']}/{r['seeds']}|")
    text += ['', '四个策略各自只有一份连续缓存；动态路径只读模型宽度、图度和本策略上一轮重算比例。没有当前轮双路试算或额外前向。', '',
             '这是已知训练轨迹上的开销可行性探索。200轮真实私有/公共SGD由E回放一次；四策略没有各自重跑SGD，因此不报告新的整体训练加速、独立质量增益或未见种子确认。', '',
             '逐轮核对全量关系、候选成员、历史E训练摘要、消息字节和接收计数；保存摘要可审计一致性，完整缓存数组未落盘，不能仅凭JSON重新证明数组内容。', '',
             '初始化含全量教师前向与缓存创建；协议初始化单列，汇总 generation_exchange_setup_seconds 包含它。公共/私有训练、oracle、摘要、评估和准备成本不计入关系生成计时。', '',
             '策略收益需与静态选择比较；策略启发式不保证有效。已有种子只作探索，规则冻结后仍须新种子复核。通信编码相同，预期消息完全相同；不宣称额外通信节省。', '',
             'smoke为小配置路径检查，不能作为性能结论。固定成员/临时聚合者固定为client0、可靠内存消息；无真实网络、选举或掉线实验。']
    (output/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')


def references(reference, preset):
    env, done = load_json(reference/'environment.json'), load_json(reference/'completed.json')
    validate_environment(env)
    if (env['preset']!=preset or env['suite']!='graph' or done['mismatches']!=0
            or done['case_count']!=9 or done['method_runs']!=27):
        raise ValueError('Expected completed three-degree graph reference')
    for name, checksum in done['file_hashes'].items():
        if Path(name).name!=name or sha(reference/name)!=checksum:
            raise ValueError('Reference artifact changed')
    plan=[from_json(v) for v in env['plan']]
    if (len(plan)!=3 or {c.degree for c in plan}!={1,4,8}
            or len({c.samples for c in plan})!=1 or env['seeds']!=[404,505,606]):
        raise ValueError('Reference plan differs')
    directories={s:verify_marker(load_json(reference/f'prepared_{s}.json')) for s in env['seeds']}
    cases={(c.case_id,s):checked_case(reference/f'{c.case_id}_seed_{s}.json',c,s,directories[s])
           for c in plan for s in env['seeds']}
    return env,plan,directories,cases


def save_case(path, case):
    temporary=path.with_suffix('.json.part')
    # A partial case is retrained from round 1; finalized .json is never replaced.
    temporary.write_text(json.dumps(case,indent=2),encoding='utf-8')
    if path.exists(): raise FileExistsError(path)
    temporary.replace(path)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset', choices=('full','smoke'), default='full')
    ap.add_argument('--reference',type=Path); ap.add_argument('--output',type=Path)
    ap.add_argument('--check-only',action='store_true'); ap.add_argument('--resume',action='store_true')
    args=ap.parse_args()
    default='results_graph' if args.preset=='full' else 'validation_smoke_20261030'
    ref=(args.reference or ROOT/f'experiments/graph_density/{default}').resolve()
    output=(args.output or ROOT/f'experiments/path_selection/results_{args.preset}').resolve()
    if output==ref or ref in output.parents or output in ref.parents:
        raise ValueError('Output must be separate from reference')
    env,plan,directories,refs=references(ref,args.preset)
    identity=dict(reference=str(ref),reference_completion_sha256=sha(ref/'completed.json'),
                  source_hashes=sources(),core_source_hashes=env['source_hashes'],preset=args.preset,rule=RULE)
    if args.resume:
        if load_json(output/'environment.json')!=identity: raise ValueError('Resume identity changed')
    elif output.exists() and any(output.iterdir()):
        raise FileExistsError('Use a fresh output or --resume')
    print('Verified 9 references/assets. Four independent continuous-cache policies; rule frozen; no same-round probes.',flush=True)
    if args.check_only: return
    output.mkdir(parents=True,exist_ok=True)
    if not args.resume: json_write_new(output/'environment.json',identity)
    cases=[]
    with threadpool_limits(limits=plan[0].threads):
        for seed in env['seeds']:
            configs={c.case_id:c for c in plan}
            for case_id in env['execution_order'][str(seed)]:
                cfg=configs[case_id];path=output/f'{case_id}_seed_{seed}.json';refcase=refs[(case_id,seed)]
                if path.exists():
                    case=load_json(path);check_case(case,cfg,seed,identity,refcase)
                    print(f'Preserved {case_id} seed={seed}',flush=True)
                else:
                    case=seal_payload(dict(**replay(directories[seed],cfg,refcase),identity=identity))
                    check_case(case,cfg,seed,identity,refcase);save_case(path,case)
                cases.append(case);report(output,cases)
    done=dict(case_count=len(cases),shared_training_trajectories=len(cases),policy_replays=len(cases)*len(POLICIES),
              relation_comparisons=sum(c['relation_comparisons'] for c in cases),
              candidate_membership_comparisons=sum(c['candidate_membership_comparisons'] for c in cases),
              mismatches=0,files={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='completed.json'},
              note='Exploratory snapshot replay, not end-to-end speed or new-seed confirmation')
    (output/'completed.json').write_text(json.dumps(done,indent=2),encoding='utf-8')
    print(f'Completed: {output / "report.md"}',flush=True)


if __name__=='__main__': main()
