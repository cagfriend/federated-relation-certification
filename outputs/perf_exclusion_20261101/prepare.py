import sys,json,csv,hashlib,zipfile,base64,shutil,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R));H=Path(__file__).parent;S=H/'stage';O=R/'experiments/perf_confirmation/results_full'
from experiments.perf_confirmation.report import aggregate,paired_summary,_write_csv
from experiments.public_scaling.util import load_json
def put(rel,text):
 p=S/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
def cp(p):
 q=S/p.relative_to(R);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
excluded=lambda r:(r['partition'],r['seed'],r['case_id'])==('dirichlet_0.1',909,'m16384_fixed8_priv2048')
runs=[load_json(p) for p in sorted((O/'runs').glob('*.json'))];assert len(runs)==72
retained=[r for r in runs if not excluded(r)];removed=[r for r in runs if excluded(r)];assert len(removed)==6 and len(retained)==66
rows,seeds,paired,noise,guards=aggregate(retained);summaries=paired_summary(paired)
dest=H/'adjusted';dest.mkdir(exist_ok=True)
for name,data in [('runs.csv',rows),('seed_summary.csv',seeds),('paired_cost.csv',paired),('paired_summary.csv',summaries),('timing_noise.csv',noise)]:_write_csv(dest/name,data)
# Quality keeps all six pairs; only timing was excluded.
quality=aggregate(runs)[4];_write_csv(dest/'quality_guardrails_all_original.csv',quality)
ex=dict(date='2026-11-01',reason='User requested temporary timing exclusion pending controlled retest after run-level variability and battery-state diagnostics',post_hoc=True,not_preregistered_pause_exclusion=True,scope=dict(partition='dirichlet_0.1',seed=909,case_id='m16384_fixed8_priv2048',methods=['B','E','D'],repeats=[0,1]),excluded_runs=6,retained_runs=66,quality_and_correctness_unchanged=True,replacement_runs_used=False,preregistered_strong_noniid_confirmation='pending retest; only two timing seeds retained',raw_files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((O/'runs').glob('*.json'))})
put('outputs/perf_exclusion_20261101/EXCLUSION.json',json.dumps(ex,indent=2))
section='''## 当前省时统计：异常整组暂时排除，待补测

更新：2026-11-01，按用户明确要求，将强非IID、seed909、2048档整个配对组（B/E/D × 两次重复，共6次运行）从当前省时、技术重复噪声和含准备成本统计中暂时排除，剩66次运行。IID三个seed和强非IID完整档三个seed仍保留。

这是事后指定的整组排除，不是预注册中的暂停轮剔除，也没有确认异常由休眠造成。原72次数据、原始报告和机械判定均保留供追溯；原“两划分均确认”不能作为排除后的当前结论。强非IID2048现只剩seed707/808，三seed预注册确认状态改为**待补测**。本次诊断重跑不替换原重复、不加入主统计。质量与正确性仍按完整原始记录报告，六组质量护栏通过。

以下为重复先平均、seed配对后取中位；正数为D省时。

|划分|档位|保留seed数|D/B完整头省时|D/E完整头省时|D/B含准备省时|D/E含准备省时|胜出D/B、D/E|
|---|---|---:|---:|---:|---:|---:|---|
'''
for part,label in [('iid','IID'),('dirichlet_0.1','强非IID')]:
 for tier in ('2048','full'):
  b=next(r for r in summaries if (r['partition'],r['case_id'],r['comparison'])==(part,'m16384_fixed8_priv'+tier,'D_over_B'));e=next(r for r in summaries if (r['partition'],r['case_id'],r['comparison'])==(part,'m16384_fixed8_priv'+tier,'D_over_E'))
  section+=f"|{label}|{tier}|{b['paired_seeds']}|{100*(1-b['head_pipeline_seconds_median_ratio']):.2f}%|{100*(1-e['head_pipeline_seconds_median_ratio']):.2f}%|{100*(1-b['with_shared_preparation_seconds_median_ratio']):.2f}%|{100*(1-e['with_shared_preparation_seconds_median_ratio']):.2f}%|{b['head_wins']}/{b['paired_seeds']}、{e['head_wins']}/{e['paired_seeds']}|\n"
section+='''
### 异常与诊断重跑记录

异常组强非IIDseed909/2048：E原两次完整头55.99/105.19秒，相对重复差61.05%；B为81.98/124.43秒，D为55.02/88.52秒。较慢重复在整个200轮持续变慢，不能以单轮暂停解释；原实验未记录供电和CPU频率。

|方法|异常seed909诊断重跑秒|正常seed808原两次均值秒|正常seed808诊断重跑秒|808变慢幅度|
|---|---:|---:|---:|---:|
|B|98.33|72.07|118.57|64.54%|
|E|76.98|60.78|91.79|51.02%|
|D|75.00|58.44|85.73|46.71%|

seed909重跑D/B省23.73%、D/E省2.58%；seed808重跑D/B省27.70%、D/E省6.59%。两个重跑均保持各自原非计时轨迹和方法专属计数。808诊断全程电源日志ACLineStatus=0（未插电）、电量87%–92%、省电模式未开启。909诊断未采集系统电源日志，用户对供电条件的说明不能替代频率监测。正常组在电池下也共同变慢，支持运行条件影响的解释，但不能据不同seed单次诊断证明电源因果。

**待补测：** 用户具备条件后，在固定供电、电源模式和负载下预先确定补测协议，再补强非IID909/2048整组。保留旧数据，不事后挑更快一次替换。当前没有启动补测。seed808原正式数据未因诊断结果被排除；本次排除范围仅上述909/2048整组。

主要统计：[调整后CSV](adjusted/paired_summary.csv)；规则：[EXCLUSION.json](EXCLUSION.json)。原始预注册报告是历史完整数据口径，当前摘要以上述排除口径为准。
'''
put('outputs/perf_exclusion_20261101/REPORT.md','# 省时统计临时排除与诊断记录\n\n'+section)
put('experiments/perf_confirmation/results_full/EXCLUSION_NOTICE.md',section.replace('(adjusted/paired_summary.csv)','(../../../outputs/perf_exclusion_20261101/adjusted/paired_summary.csv)').replace('(EXCLUSION.json)','(../../../outputs/perf_exclusion_20261101/EXCLUSION.json)'))
put('outputs/perf_exclusion_20261101/adjusted/summary.json',json.dumps(dict(post_hoc_exclusion=True,retained_runs=66,paired_summary=summaries,formal_verdict='IID remains confirmed; strong noniid candidate pending retest',quality_guardrails_from_all_original_runs=quality),indent=2))
for p in dest.iterdir():cp(p)
cp(H/'prepare.py')
archives=[]
for dirname in ('perf_confirmation_rerun_20261101','perf_confirmation_normal_rerun_20261101'):
 folder=R/'outputs'/dirname
 for p in folder.iterdir():
  if p.is_file():cp(p)
 paths=sorted((folder/'runs').glob('*.json'));rel=f'archives/{dirname}.zip';p=S/rel;p.parent.mkdir(exist_ok=True);files=[]
 with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for src in paths:
   b=src.read_bytes();i=zipfile.ZipInfo(src.relative_to(R).as_posix(),(2026,11,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;z.writestr(i,b,compresslevel=9);files.append(dict(path=src.relative_to(R).as_posix(),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b)))
 with zipfile.ZipFile(p) as z:
  for src in paths:assert z.read(src.relative_to(R).as_posix())==src.read_bytes()
 archives.append(dict(archive=rel,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),files=files))
put('archives/ARCHIVE_MANIFEST.json',json.dumps(json.loads((H/'base/archives/ARCHIVE_MANIFEST.json').read_text(encoding='utf-8'))+archives,indent=2))
for name,marker in [('README.md','## 新完成：独立性能确认（2026-11-01）'),('docs/EXPERIMENTS.md','## 12. 独立性能确认')]:
 t=(H/'base'/name).read_text(encoding='utf-8');assert marker in t
 put(name,t[:t.index(marker)]+section.replace('(adjusted/paired_summary.csv)','('+('' if name=='README.md' else '../')+'outputs/perf_exclusion_20261101/adjusted/paired_summary.csv)').replace('(EXCLUSION.json)','('+('' if name=='README.md' else '../')+'outputs/perf_exclusion_20261101/EXCLUSION.json)'))
notice='> 当前状态（2026-11-01）：用户要求暂排强非IIDseed909/2048整组6次计时；强非IID候选仅剩2个seed，预注册确认待补测。以下完整72次结果为历史未排除口径。[当前统计](../perf_exclusion_20261101/REPORT.md)。\n\n'
put('outputs/perf_confirmation_results_20261101/RESULTS_REVIEW.md',notice+(H/'base/outputs/perf_confirmation_results_20261101/RESULTS_REVIEW.md').read_text(encoding='utf-8'))
n=(H/'base/docs/NEXT_EXPERIMENTS.md').read_text(encoding='utf-8');a=n.index('## 2.');b=n.index('## 3.',a)
n=n[:a]+'''## 2. 独立性能确认：IID保留，强非IID候选待补测

按用户2026-11-01指示，暂排强非IIDseed909/2048整组B/E/D两次重复，共6次计时。剩2个seed的D/B完整头省21.50%、D/E省5.95%；属于事后调整描述，不满足原三seed确认完整性。原始72次文件和原预注册判定保留为历史记录；异常及909、808诊断重跑均已公开。

等待用户具备条件后确定固定供电的补测协议，不能用事后更快一次替换原重复。IID候选原三seed判定保留。第二数据场景仍为后续方向，但不把待补测状态写成全部确认。[当前统计与排除规则](../outputs/perf_exclusion_20261101/REPORT.md)。

'''+n[b:]
n=n.replace('|已完成72次独立进程，两划分均确认|','|已运行72次；IID保留，强非IID候选排除1组待补测|')
n=n.replace('第2项独立性能确认现已完成，2048在冻结场景中得到确认，仍非普适最优。','第2项已运行，但强非IID候选现因临时排除待补测，不能称两划分均已确认。')
if '## 当前行动建议' in n:n=n[:n.index('## 当前行动建议')]+'''## 当前行动建议

等待用户具备条件后补测强非IID909/2048计时。当前66次保留统计单列，所有原始数据和诊断结果保留，不替换预注册重复。第二数据场景仍待推进，静态选路复核继续暂缓。本次未启动任何补测或新实验。
'''
put('docs/NEXT_EXPERIMENTS.md',n)
expected=[];packets=[]
for p in sorted(S.rglob('*')):
 if not p.is_file():continue
 b=p.read_bytes();rel=p.relative_to(S).as_posix();expected.append(dict(path=rel,sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()))
 if p.suffix=='.zip':packets.append(dict(kind='blob',path=rel,content=base64.b64encode(b).decode()))
 elif p.name=='power_scheme.txt':packets.append(dict(kind='blob',path=rel,content=base64.b64encode(b).decode()))
 else:packets.append(dict(kind='tree',entries=[dict(path=rel,mode='100644',type='blob',content=b.decode('utf-8-sig'))]))
 # Text decoded with utf-8-sig can remove BOM: match actual staged payload.
 if packets[-1]['kind']=='tree':
  b=packets[-1]['entries'][0]['content'].encode();expected[-1]['sha']=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
t=H/'transport';t.mkdir(exist_ok=True);idx=[]
for i,p in enumerate(packets):
 s=json.dumps(p,ensure_ascii=True);(t/f'{i}.json').write_text(s,encoding='ascii');idx.append(dict(index=i,chars=len(s),kind=p['kind']))
(H/'index.json').write_text(json.dumps(idx));(H/'expected.json').write_text(json.dumps(expected));print(json.dumps(dict(files=len(expected),retained_runs=66,summary=[r for r in summaries if r['partition']=='dirichlet_0.1' and r['private_limit']==2048]),indent=2))
