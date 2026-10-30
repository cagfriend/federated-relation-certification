"""Replay one real E training trajectory; diagnose independent E/D caches on its snapshots."""
import argparse
import csv
import json
import math
from pathlib import Path
from time import perf_counter

import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.certification import RelationGenerator, hard_relations
from experiments.public_scaling.config import from_json
from experiments.public_scaling.data import Prepared, sha, json_write_new
from experiments.public_scaling.engine import Method, evaluate
from experiments.public_scaling.run import checked_case, validate_environment, verify_marker
from experiments.public_scaling.util import load_json, seal_payload, validate_payload
from .profiler import PHASES, ProfiledGenerator

ROOT=Path(__file__).resolve().parents[2]


def own_sources():
    return {p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}


def same_cache(a,b):
    if a.round!=b.round: raise AssertionError('Cache round differs')
    for key in a.persistent_arrays():
        if not np.array_equal(getattr(a,key),getattr(b,key)):
            raise AssertionError(f'Instrumentation changed cache: {key}')


def check_checkpoint(case,config,seed,identity,reference):
    validate_payload(case)
    expected={(r,i,n) for r in range(1,config.rounds+1) for i in range(len(config.dimensions)) for n in ('E','D')}
    actual=[(r['round'],r['client'],r['method']) for r in case['records']]
    if (case.get('identity')!=identity or case['seed']!=seed or case['case_id']!=config.case_id
            or case['config']!=config.json() or case['mismatches']!=0
            or len(actual)!=len(expected) or set(actual)!=expected):
        raise ValueError('Checkpoint identity or coverage differs')
    if case['quality']!=[m for m in reference['metrics'] if m['method']=='E']:
        raise ValueError('Checkpoint quality differs from source')
    for r in case['records']:
        timers=[r[k] for k in ('profiled_wall_seconds','plain_wall_seconds','unassigned_seconds')]+list(r['phase_seconds'].values())
        if any(not math.isfinite(t) or t<0 for t in timers) or set(r['phase_seconds'])!=set(PHASES):
            raise ValueError('Invalid checkpoint times')
        if abs(r['profiled_wall_seconds']-sum(r['phase_seconds'].values())-r['unassigned_seconds'])>1e-9 or r['bootstrap']!=(r['round']==1):
            raise ValueError('Invalid phase accounting')
        old=next(q for q in reference['round_records'] if q['round']==r['round'] and q['method']==r['method'])['client_statistics'][r['client']]
        if any(r['statistics'][k]!=old[k] for k in ('forward_endpoints','candidate_entries','certified_edges_before_refresh')):
            raise ValueError('Checkpoint refresh statistics differ from source')
    if case['relation_comparisons']!=4*config.rounds*len(config.dimensions)*config.samples*config.degree//2:
        raise ValueError('Wrong oracle coverage')


def replay(directory,config,reference,*,fixture=False):
    data=Prepared(directory,config,allow_test_fixture=fixture)
    try:
        trainer=Method('E',data,config)
        generators={}; records=[]; quality=[]; checks=0
        historical={(r['round'],r['method']):r for r in reference['round_records']}
        for rnd in range(1,config.rounds+1):
            trained,_,snapshots=trainer.step(rnd)
            old=historical[(rnd,'E')]
            if trained['head_digest_after_public']!=old['head_digest_after_public'] or trained['traffic']!=old['traffic']:
                raise AssertionError('Replay diverged from saved E training trajectory')
            for client,(w,b) in enumerate(snapshots):
                oracle_labels=(data.public[client]@w.T+b).argmax(axis=1)
                oracle=hard_relations(oracle_labels,data.edges)
                order=[('E','plain'),('E','profiled'),('D','plain'),('D','profiled')]
                shift=(data.seed+rnd+client)%4; order=order[shift:]+order[:shift]
                output={}
                for name,kind in order:
                    key=(client,name,kind); mode={'E':'point','D':'relation'}[name]
                    start=perf_counter()
                    if rnd==1:
                        cls=ProfiledGenerator if kind=='profiled' else RelationGenerator
                        generator=cls(data.public[client],w,b,data.edges,mode)
                        generators[key]=generator
                        relation=generator.initial_relations
                        del generator.initial_relations
                        stats={'forward_endpoints':config.samples,'candidate_entries':config.samples*config.classes,'certified_edges_before_refresh':0}
                    else:
                        generator=generators[key]; relation,stats=generator.generate(w,b)
                    wall=perf_counter()-start
                    output[(name,kind)]=(wall,stats)
                    if not np.array_equal(relation,oracle):raise AssertionError('Incorrect relation')
                    if not np.all(RelationGenerator.candidate_matrix(generator)[np.arange(config.samples),oracle_labels]):
                        raise AssertionError('Current winner excluded')
                    expected=historical[(rnd,name)]['client_statistics'][client]
                    if any(stats[k]!=expected[k] for k in ('forward_endpoints','candidate_entries','certified_edges_before_refresh')):
                        raise AssertionError('Cache refresh path differs from saved method')
                    checks+=len(oracle)
                for name in ('E','D'):
                    plain=generators[(client,name,'plain')]; prof=generators[(client,name,'profiled')]
                    same_cache(plain,prof)
                    wall,stats=output[(name,'profiled')]
                    if stats!=output[(name,'plain')][1]:raise AssertionError('Statistics differ')
                    phases={k:0.0 if rnd==1 else prof.phase_seconds[k] for k in PHASES}
                    other=wall-sum(phases.values())
                    if other < -1e-9:raise AssertionError('Nested or overlapping phase timers')
                    records.append(dict(round=rnd,client=client,width=config.dimensions[client],method=name,
                        bootstrap=rnd==1,profiled_wall_seconds=wall,plain_wall_seconds=output[(name,'plain')][0],
                        unassigned_seconds=other,phase_seconds=phases,statistics=stats,
                        diagnostics={} if rnd==1 else prof.diagnostics.copy()))
            if rnd%config.eval_every==0 or rnd==config.rounds:
                metrics={'method':'E','round':rnd,**evaluate(trainer.heads,data,config)}
                expected=next(m for m in reference['metrics'] if m['round']==rnd and m['method']=='E')
                if metrics!=expected:raise AssertionError('Quality differs from historical E')
                quality.append(metrics)
            if rnd%10==0 or rnd==config.rounds:print(f'{config.case_id} seed={data.seed}: {rnd}/{config.rounds}',flush=True)
        return dict(case_id=config.case_id,seed=data.seed,config=config.json(),records=records,
                    relation_comparisons=checks,quality=quality,mismatches=0)
    finally:data.close()


def report(output,cases):
    import statistics as st
    groups={}; rows=[]
    for case in cases:
        for name in ('E','D'):
            rr=[r for r in case['records'] if r['method']==name and not r['bootstrap']]
            phase={p:sum(r['phase_seconds'][p] for r in rr) for p in PHASES}
            plain=sum(r['plain_wall_seconds'] for r in rr); prof=sum(r['profiled_wall_seconds'] for r in rr)
            row=dict(case_id=case['case_id'],seed=case['seed'],method=name,plain_generation_seconds=plain,
                instrumented_generation_seconds=prof,observed_instrumented_over_plain=prof/plain,
                unassigned_seconds=sum(r['unassigned_seconds'] for r in rr),
                selected_endpoints=sum(r['statistics']['forward_endpoints'] for r in rr),
                unresolved_endpoint_union=None if name=='E' else sum(r['diagnostics']['unresolved_endpoint_union'] for r in rr),
                bootstrap_plain_seconds=sum(r['plain_wall_seconds'] for r in case['records'] if r['method']==name and r['bootstrap']),
                **{p+'_seconds':v for p,v in phase.items()})
            rows.append(row)
    for case_id in sorted({r['case_id'] for r in rows}):
        groups[case_id]={n:{k:st.median(r[k] for r in rows if r['case_id']==case_id and r['method']==n)
                           for k in rows[0] if k not in ('case_id','seed','method','unresolved_endpoint_union')}
                         for n in ('E','D')}
    (output/'summary.json').write_text(json.dumps(groups,indent=2),encoding='utf-8')
    with (output/'summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    text=['# E/D成本诊断','',
        '仅用于机制诊断；每组先汇总各seed，再列中位数。所有阶段排除首轮全量初始化，初始化另列。控制组同快照、独立缓存，四条求值路径轮换顺序。', '',
        '|配置|方法|控制生成秒|带计时生成秒|变化界|候选矩阵|位集合|认证检查|端点收集|教师重算|缓存更新|最终关系/统计|',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    text.insert(2,f'已汇总{len(cases)}/9个配置-seed；只有completed.json存在且校验通过才算全部完成。\n')
    if any(c['config']['samples']!=4096 or c['config']['rounds']!=200 for c in cases):
        text.insert(2,'**缩小配置的路径验证，不作正式性能结论。**\n')
    for case_id,g in groups.items():
        for name,s in g.items():
            vals=[s['plain_generation_seconds'],s['instrumented_generation_seconds']]+[s[p+'_seconds'] for p in PHASES]
            text.append('|'+case_id+'|'+name+'|'+'|'.join(f'{v:.6f}' for v in vals)+'|')
    text+=['','各列独立取中位数，因此表格各阶段中位数不保证相加等于总中位数；逐seed summary.csv可以做精确分解。', '',
        'unassigned_seconds含计时器/上下文管理器、计数采集和未分段语句等成本，不能等同于纯计时器开销。控制/带计时之比也受缓存和执行负载影响，不从阶段耗时中扣除它。', '',
        '这里没有自适应策略，也不重用带计时训练流程宣称加速。最终净收益请读上一轮未插桩的正式图密度结果。所有缓存逐轮与未插桩同方法逐数组相等；关系由全量oracle核对；E训练摘要、消息、评估与保存轨迹一致。', '',
        '教师阶段包括特征索引、矩阵乘、有限值检查和argmax；缓存阶段包括间隔重建和引用预算更新，不能称为纯算子耗时。E与D各自缓存独立，禁止把E缓存拿给D作公平比较。']
    (output/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset',choices=('full','smoke'),default='full')
    ap.add_argument('--reference',type=Path)
    ap.add_argument('--output',type=Path)
    ap.add_argument('--resume',action='store_true');ap.add_argument('--check-only',action='store_true')
    args=ap.parse_args()
    default_ref='results_graph' if args.preset=='full' else 'validation_smoke_20261030'
    reference=(args.reference or ROOT/f'experiments/graph_density/{default_ref}').resolve()
    output=(args.output or ROOT/f'experiments/cost_diagnostics/results_{args.preset}').resolve()
    if output==reference or reference in output.parents or output in reference.parents:raise ValueError('Use separate output')
    env,done=load_json(reference/'environment.json'),load_json(reference/'completed.json')
    validate_environment(env)
    if env['preset']!=args.preset or env['suite']!='graph' or done['mismatches']!=0:raise ValueError('Wrong reference suite/preset')
    for name,h in done['file_hashes'].items():
        if Path(name).name!=name or sha(reference/name)!=h:raise ValueError('Reference changed')
    plan=[from_json(v) for v in env['plan']]
    if len(plan)!=3 or {c.degree for c in plan}!={1,4,8} or len({c.samples for c in plan})!=1 or env['seeds']!=[404,505,606]:
        raise ValueError('Expected frozen three-degree, three-seed plan')
    if done['case_count']!=9 or done['method_runs']!=27:raise ValueError('Incomplete reference')
    identity=dict(reference=str(reference),reference_completion_sha256=sha(reference/'completed.json'),
                  source_hashes=own_sources(),core_source_hashes=env['source_hashes'],preset=args.preset)
    if args.resume:
        if load_json(output/'environment.json')!=identity:raise ValueError('Resume identity changed')
    elif output.exists() and any(output.iterdir()):raise FileExistsError('Use new output or --resume')
    # Verify all assets and all historical case payloads before any new training.
    directories={seed:verify_marker(load_json(reference/f'prepared_{seed}.json')) for seed in env['seeds']}
    refs={(c.case_id,s):checked_case(reference/f'{c.case_id}_seed_{s}.json',c,s,directories[s]) for c in plan for s in env['seeds']}
    print(f'Diagnose {len(refs)} E trajectories, independent plain/profiled E and D caches; no adaptive selection',flush=True)
    if args.check_only:return
    output.mkdir(parents=True,exist_ok=True)
    if not args.resume:json_write_new(output/'environment.json',identity)
    cases=[]
    with threadpool_limits(limits=plan[0].threads):
        for seed in env['seeds']:
            configs={c.case_id:c for c in plan}
            for case_id in env['execution_order'][str(seed)]:
                config=configs[case_id];path=output/f'{case_id}_seed_{seed}.json'
                if path.exists():
                    case=load_json(path)
                    check_checkpoint(case,config,seed,identity,refs[(case_id,seed)])
                    print(f'Preserved {case_id} seed={seed}',flush=True)
                else:
                    case=seal_payload(dict(**replay(directories[seed],config,refs[(case_id,seed)]),identity=identity))
                    check_checkpoint(case,config,seed,identity,refs[(case_id,seed)])
                    json_write_new(path,case)
                cases.append(case);report(output,cases)
    completed=dict(case_count=len(cases),training_trajectories=len(cases),mismatches=0,
                   relation_comparisons=sum(c['relation_comparisons'] for c in cases),
                   note='Instrumented mechanism diagnosis, not an end-to-end speed benchmark',
                   files={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='completed.json'})
    (output/'completed.json').write_text(json.dumps(completed,indent=2),encoding='utf-8')
    print(f'Complete: {output / "report.md"}',flush=True)


if __name__=='__main__':main()
