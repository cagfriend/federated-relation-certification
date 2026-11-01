import sys,json,copy,hashlib,zipfile,base64,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R));H=Path(__file__).parent;S=H/'stage';S.mkdir(exist_ok=True)
from experiments.perf_confirmation.report import aggregate,paired_summary,_write_csv
from experiments.perf_confirmation.engine import method_signature
from experiments.public_scaling.util import load_json
def put(n,t):
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t,encoding='utf-8')
def cp(p):
 q=S/p.relative_to(R);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
O=R/'experiments/perf_confirmation/results_full';original=[load_json(p) for p in sorted((O/'runs').glob('*.json'))]
runs=[r for r in original if not (r['partition']=='dirichlet_0.1' and r['seed']==909 and 'priv2048' in r['case_id'])];assert len(runs)==66
for seed in (909,808):
 for p in sorted((R/f'outputs/perf_controlled_seed{seed}_20261101/runs').glob('*.json')):
  r=load_json(p);old=next(x for x in original if x['partition']==r['partition'] and x['seed']==seed and x['case_id']==r['case_id'] and x['method']==r['method']);assert method_signature(r)==method_signature(old)
  r=copy.deepcopy(r);r['repeat']=2;r['source_record']=p.relative_to(R).as_posix();runs.append(r)
assert len(runs)==72
rows,seeds,paired,noise,guards=aggregate(runs);sums=paired_summary(paired)
for n,d in [('runs.csv',rows),('seed_summary.csv',seeds),('paired_cost.csv',paired),('paired_summary.csv',sums),('quality_guardrails.csv',guards)]:
 p=S/'outputs/perf_integrated_20261101'/n;p.parent.mkdir(parents=True,exist_ok=True);_write_csv(p,d)
section='''## 当前结果：已纳入插电补测

2026-11-01按用户要求纳入本次两组三元组插电补测。当前统计=此前保留66次正式运行＋本次6次插电运行，共72次；原异常强非IIDseed909/2048的6次正式计时继续排除，旧的两次电池状态诊断不参与统计。

**重复数说明：** 强非IID2048候选seed707每方法2次、seed808每方法3次、seed909每方法1次；其余配置每方法2次。每个seed内先平均，再取seed配对比的中位，不按运行次数加权seed。本次是事后补测汇总，不冒充原先固定每格2次的预注册确认；当前三seed均可报告描述性省时，但原设计的正式确认不能由不等重复数自动恢复。质量护栏仍6/6通过。

|划分|档位|D/B完整头省时|D/E完整头省时|D/B含准备省时|D/E含准备省时|seed胜出D/B、D/E|
|---|---|---:|---:|---:|---:|---|
'''
for part,label in [('iid','IID'),('dirichlet_0.1','强非IID')]:
 for cap in ('2048','full'):
  b=next(x for x in sums if (x['partition'],x['case_id'],x['comparison'])==(part,'m16384_fixed8_priv'+cap,'D_over_B'));e=next(x for x in sums if (x['partition'],x['case_id'],x['comparison'])==(part,'m16384_fixed8_priv'+cap,'D_over_E'))
  section+=f"|{label}|{cap}|{100*(1-b['head_pipeline_seconds_median_ratio']):.2f}%|{100*(1-e['head_pipeline_seconds_median_ratio']):.2f}%|{100*(1-b['with_shared_preparation_seconds_median_ratio']):.2f}%|{100*(1-e['with_shared_preparation_seconds_median_ratio']):.2f}%|{b['head_wins']}/3、{e['head_wins']}/3|\n"
section+='''
### 补测与异常记录

插电复测：seed909的B/E/D头部为76.72/63.51/59.37秒，D/B省22.61%、D/E省6.52%；seed808为77.24/66.02/61.98秒，D/B省19.76%、D/E省6.13%。两组日志均全程插电、电量100%、省电模式关闭。六次非计时签名与各自原记录一致，原72份记录保留。

原seed909的E两次为55.99/105.19秒（差61.05%），同组B、D也持续变慢；此前诊断seed909为B/E/D=98.33/76.98/75.00秒，seed808未插电诊断为118.57/91.79/85.73秒（电量87%–92%）。当前插电后两组均明显加快，支持运行条件影响的解释，原运行未记录频率温度和供电，仍不能单独证明原异常原因。上述诊断计时不纳入当前省时汇总。

旧排障操作指南和待补测公告已移除。当前结果与数据选择规则集中在本报告；原预注册完整数据报告仅作历史追溯，原异常计时没有被覆盖或改写。来源与各运行摘要见INCLUSION.json；重跑原JSON无损归档。
'''
put('outputs/perf_integrated_20261101/REPORT.md','# 纳入插电补测后的省时统计\n\n'+section)
sources=[]
for r in runs:
 p=R/r['source_record'] if 'source_record' in r else O/'runs'/f"{r['partition']}_{r['case_id']}_seed_{r['seed']}_{r['method']}_rep{r['repeat']}.json"
 sources.append(dict(path=p.relative_to(R).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
put('outputs/perf_integrated_20261101/INCLUSION.json',json.dumps(dict(post_hoc=True,retained_original_runs=66,controlled_runs_added=6,total=72,excluded_original_group=dict(partition='dirichlet_0.1',seed=909,private_limit=2048,methods=['B','E','D'],repeats=[0,1]),repeat_counts_candidate_strong_noniid={'707':2,'808':3,'909':1},seed_weighting='equal after within-seed mean',source_records=sources,summary=sums),indent=2))
archives=[]
for seed in (909,808):
 folder=R/f'outputs/perf_controlled_seed{seed}_20261101'
 for p in folder.iterdir():
  if p.is_file() and p.name!='power_scheme.txt':cp(p)
 paths=sorted((folder/'runs').glob('*.json'));rel=f'archives/perf_controlled_seed{seed}_20261101.zip';p=S/rel;p.parent.mkdir(exist_ok=True);files=[]
 with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for src in paths:
   b=src.read_bytes();i=zipfile.ZipInfo(src.relative_to(R).as_posix(),(2026,11,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;z.writestr(i,b,compresslevel=9);files.append(dict(path=src.relative_to(R).as_posix(),bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
 with zipfile.ZipFile(p) as z:
  for src in paths:assert z.read(src.relative_to(R).as_posix())==src.read_bytes()
 archives.append(dict(archive=rel,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),files=files))
for n in ('REPORT.md','comparison.json','compare.py','run_pair.py'):cp(R/'outputs/perf_controlled_20261101'/n)
cp(H/'prepare.py')
put('archives/ARCHIVE_MANIFEST.json',json.dumps(json.loads((H/'base/archives/ARCHIVE_MANIFEST.json').read_text(encoding='utf-8'))+archives,indent=2))
for name in ('README.md','docs/EXPERIMENTS.md'):
 t=(H/'base'/name).read_text(encoding='utf-8');marker='## 当前省时统计：异常整组暂时排除，待补测';assert marker in t
 t=t[:t.index(marker)]+section;t=t.replace('独立性能确认已完成，下一项推荐第二数据场景验证','已纳入插电补测，当前采用事后汇总，下一项推荐第二数据场景验证');put(name,t)
n=(H/'base/docs/NEXT_EXPERIMENTS.md').read_text(encoding='utf-8');a=n.index('## 2.');b=n.index('## 3.',a)
n=n[:a]+'''## 2. 插电补测已纳入当前统计

当前采用66次保留原运行＋6次插电补测，seed内平均后等权汇总。强非IID候选三seed各有2/3/1次重复，属于事后补测汇总，不能冒充原预注册的固定两次重复确认。原始异常数据及全部诊断保存；不再保留排障操作指南。当前省时见[合并报告](../outputs/perf_integrated_20261101/REPORT.md)。

'''+n[b:]
n=n.replace('|已运行72次；IID保留，强非IID候选排除1组待补测|','|已纳入插电补测；当前事后汇总，共72次|')
n=n.replace('第2项已运行，但强非IID候选现因临时排除待补测，不能称两划分均已确认。','第2项已纳入插电补测，按公开事后汇总报告，原预注册确认与当前统计区分。')
if '## 当前行动建议' in n:n=n[:n.index('## 当前行动建议')]+'''## 当前行动建议

插电补测结果已纳入当前统计，下一项推荐第二数据集与公共样本分布验证。若以后需要恢复严格预注册确认，另行冻结等重复数方案；不把它作为计算研究继续推进的前提。质量只作护栏，静态选路复核继续暂缓。本次未启动新实验。
'''
put('docs/NEXT_EXPERIMENTS.md',n)
put('experiments/perf_confirmation/results_full/CURRENT_RESULTS.md','当前统计已纳入插电补测，原report.md是历史未调整口径。详见[当前报告](../../../outputs/perf_integrated_20261101/REPORT.md)，规则与来源见INCLUSION.json。\n')
put('outputs/perf_confirmation_results_20261101/RESULTS_REVIEW.md','> 当前已纳入插电补测，采用[事后汇总](../perf_integrated_20261101/REPORT.md)。下文为原始72次历史口径，不是当前选择后的预注册确认。\n\n'+(H/'base/outputs/perf_confirmation_results_20261101/RESULTS_REVIEW.md').read_text(encoding='utf-8').split('\n\n',1)[1])
deletes=['experiments/perf_confirmation/results_full/EXCLUSION_NOTICE.md','outputs/perf_exclusion_20261101/REPORT.md','outputs/perf_confirmation_rerun_20261101/REPORT.md','outputs/perf_confirmation_normal_rerun_20261101/REPORT.md']
(H/'deletes.json').write_text(json.dumps(deletes))
expected=[];packets=[]
for p in sorted(S.rglob('*')):
 if not p.is_file():continue
 b=p.read_bytes();rel=p.relative_to(S).as_posix();expected.append(dict(path=rel,sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()));packets.append(dict(kind='blob',path=rel,content=base64.b64encode(b).decode()) if p.suffix=='.zip' else dict(kind='tree',entries=[dict(path=rel,mode='100644',type='blob',content=b.decode('utf-8'))]))
t=H/'transport';t.mkdir(exist_ok=True);idx=[]
for i,p in enumerate(packets):
 s=json.dumps(p,ensure_ascii=True);(t/f'{i}.json').write_text(s,encoding='ascii');idx.append(dict(index=i,kind=p['kind'],chars=len(s)))
(H/'index.json').write_text(json.dumps(idx));(H/'expected.json').write_text(json.dumps(expected));print(json.dumps(dict(files=len(expected),deletes=deletes,summary=[r for r in sums if r['partition']=='dirichlet_0.1' and r['private_limit']==2048]),indent=2))
