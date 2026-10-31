import json,csv,statistics,hashlib,zipfile,shutil,base64
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent;STAGE=HERE/'github_stage';OUT=ROOT/'experiments/private_workload/results_full'
def put(rel,text):
 p=STAGE/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
def copy(p):
 d=STAGE/p.relative_to(ROOT);d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,d)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def main():
 STAGE.mkdir(exist_ok=True);base=HERE/'remote_base';rows=list(csv.DictReader((OUT/'paired_cost.csv').open()));summary=list(csv.DictReader((OUT/'summary.csv').open()));guards=list(csv.DictReader((OUT/'quality_guardrails.csv').open()))
 section='''18组、54条B/E/D训练及18次隔离内存回放完成；IID/强非IID、三个既有seed，M16384、degree1、K10、公共固定8步。仅改变每客户端每轮私有头部预算：完整约7270 / 2048 / 1024，编码器仍由完整私有集预训练并冻结。

下表是同配置、同seed配对比值的三seed中位，含初始化；正值为D省时，负值为D较慢。预算削减的自身收益另列于workload_effects.csv，不算认证贡献。

|划分|私有上限|D/B完整头省时|D/B含准备省时|D/E完整头省时|D/E头胜出|
|---|---|---:|---:|---:|---:|
'''
 for part,label in [('iid','IID'),('dirichlet_0.1','强非IID')]:
  for cap in ('full','2048','1024'):
   cid='m16384_fixed8_priv'+cap
   def select(comp,metric):return [r for r in rows if (r['partition'],r['case_id'],r['comparison'],r['measure'])==(part,cid,comp,metric)]
   def save(comp,metric):return 100*(1-statistics.median(float(r['ratio_D_over_reference']) for r in select(comp,metric)))
   wins=sum(float(r['ratio_D_over_reference'])<1 for r in select('D_over_E','head_pipeline_seconds'))
   section+=f"|{label}|{cap}|{save('D_over_B','head_pipeline_seconds'):.2f}%|{save('D_over_B','with_shared_preparation_seconds'):.2f}%|{save('D_over_E','head_pipeline_seconds'):.2f}%|{wins}/3|\n"
 section+='''
**计算结论：** 降低私有工作负载使B的关系生成占比从完整档约25%升至2048档约38%、1024档约43%–45%，D/B整体省时随之扩大。但1024档D/E两个划分均3/3较慢，不能声称认证越多就一定更好；2048档是当前较合适的探索性候选。相对B完整头18/18胜出，相对E12/18胜出。三个既有seed、同进程轮换执行尚非独立性能确认，也不是并行系统轮时延。

**质量只作护栏：** 同预算B/E/D参数、关系目标和评估完全一致，认证没有引入质量差。预算缩减相对完整档：2048的IID平均ACC下降0.383/0.327/0.455个百分点，均在≤1个百分点护栏；强非IID变化−3.060/+0.760/−0.285个百分点，2/3通过，不能按总体中位数掩盖seed404失败。1024的IID下降2.09–2.40个百分点，强非IID下降25.36–27.46个百分点，6/6超护栏，不作为可接受的小幅退化方案。不得将减预算收益或损失归因于认证。

**计时边界：** 强非IID seed606/1024的B第150轮generation为36.886秒（同轨迹中位0.219秒）；IID seed505/2048的E第143轮public为15.031秒（中位0.181秒）。其他筛查点见audit.json。原因未确认，本次不擅自判为人工暂停或故障，也未排除或插补任何轮；此前public_budget中用户确认的两次暂停属于另一实验，不沿用到本轮。性能表保留全部200轮，优势仍需平衡顺序、独立进程与重复计时确认。

**资源与验证：** 同预算通信字节B/E/D一致，D较B多25.346 MiB持久数组，与E相同。18次CPU峰值回放只测完整私有档，不能推定2048/1024峰值已测；完整档D较B进程峰值约多21%，非显存或准备峰值。全部51文件摘要、18case抽样/伪标签直方图/步骤/目标/摘要/覆盖和18内存档案通过主审核验，8份报表按原执行顺序重生成逐字节相同；训练记录530841600次关系和707788800次候选检查零误差，3600历史轮×方法锚点相等。137份历史结果未改，7项单元测试通过。未重跑正式训练或独立重演全部教师前向。
'''
 review='# 私有头部工作负载：正式结果审核\n\n日期：2026-10-31。主审：本地结果与冻结源码核对；独立GPT-6 Luna/high复审见独立报告。\n\n'+section+'\n下一项建议：冻结2048为待确认候选，并保留完整档和1024反例；先补独立性能确认。强非IID2048的单seed质量越界如实保留，不以调损失追ACC作为计算研究前置条件。暂不新增实验或重启静态选路复核。\n'
 (HERE/'RESULTS_REVIEW.md').write_text(review,encoding='utf-8')
 for p in (ROOT/'experiments/private_workload').iterdir():
  if p.is_file():copy(p)
 archives=[];groups=[];derived=[]
 for p in sorted(OUT.iterdir()):
  if p.name.startswith(('iid_m','dirichlet_0.1_m')) and p.suffix=='.json':groups.append((f'archives/private_workload_raw_{p.stem}.zip',[p]))
  elif p.is_file() and p.stat().st_size>100000:derived.append(p)
  elif p.is_file():copy(p)
 if derived:groups.append(('archives/private_workload_derived.zip',derived))
 for rel,paths in groups:
  p=STAGE/rel;p.parent.mkdir(exist_ok=True);files=[]
  with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
   for src in paths:
    b=src.read_bytes();name=src.relative_to(ROOT).as_posix();info=zipfile.ZipInfo(name,(2026,10,31,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,b,compresslevel=9);files.append(dict(path=name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
  with zipfile.ZipFile(p) as z:
   assert z.testzip() is None
   for src in paths:assert z.read(src.relative_to(ROOT).as_posix())==src.read_bytes()
  archives.append(dict(archive=rel,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),files=files))
 put('archives/ARCHIVE_MANIFEST.json',json.dumps(json.loads((base/'archives/ARCHIVE_MANIFEST.json').read_text(encoding='utf-8'))+archives,ensure_ascii=False,indent=2))
 for name in ('audit_results.py','audit.json','RESULTS_REVIEW.md','independent_review.md','prepare_publication.py'):copy(HERE/name)
 for name in ('LOCAL_REVIEW.md','LOCAL_VALIDATION.json','INDEPENDENT_REVIEW.md','INSTALL_RECEIPT.json'):copy(ROOT/'outputs/private_workload_review_20261031'/name)
 link='outputs/private_workload_results_20261031/RESULTS_REVIEW.md'
 readme=(base/'README.md').read_text(encoding='utf-8').replace('下一项减少私有头部工作负载，独立性能确认与STL-10候选保留','私有头部工作负载实验已完成，下一项推荐独立性能确认，STL-10候选保留')+'\n## 新完成：私有头部工作负载与收益边界\n\n'+section+f'\n[正式审核]({link}) · [独立复审](outputs/private_workload_results_20261031/independent_review.md)\n'
 put('README.md',readme)
 put('docs/EXPERIMENTS.md',(base/'docs/EXPERIMENTS.md').read_text(encoding='utf-8')+'\n## 11. 私有头部工作负载\n\n'+section+f'\n[主审](../{link}) · [原始汇总](../experiments/private_workload/results_full/report.md) · [独立复审](../outputs/private_workload_results_20261031/independent_review.md)\n')
 nxt=(base/'docs/NEXT_EXPERIMENTS.md').read_text(encoding='utf-8')
 nxt=nxt.replace('|推荐下一项|','|已完成18组；2048为有条件候选，1024超质量护栏|',1)
 nxt=nxt.replace('## 1. 下一项：减少私有头部训练工作负载','## 1. 已完成：减少私有头部训练工作负载',1)
 start=nxt.index('## 1. 已完成：');end=nxt.index('## 2. 独立性能确认',start)
 nxt=nxt[:start]+'''## 1. 已完成：减少私有头部训练工作负载

正式18组、54条B/E/D轨迹与18次完整私有档内存回放已审核。固定M16384、degree1、K10、公共8步，私有上限完整/2048/1024；编码器始终完整私有预训练，不能称为小私有数据集实验。

2048档D/B完整头省时中位IID22.01%、强非IID22.81%；D/E省5.32%/2.83%，两个划分各3/3较快。平均ACC护栏5/6通过，强非IIDseed404下降3.06个百分点，应保留为质量越界。1024档D/B省27.72%/31.94%，但D/E慢1.26%/2.54%，平均ACC六组均越界，强非IID下降约25–27个百分点，停止将其推荐为“小幅下降”的可用配置。

所有同预算B/E/D关系、参数、目标和评估一致；计算正确性通过。预算缩减自身的收益与认证收益分开报告。原始计时存在B generation 36.89秒及E public 15.03秒离群，原因未确认，本次保留全部轮，不自行归为人工暂停或故障。

下一步只推荐第2项独立性能确认，2048是待确认候选，不是已普适最优。完整档和1024结果继续保留为边界；不为取得正ACC反复改损失，不将这次探索性计时当作独立性能复核。

证据：[正式审核](../outputs/private_workload_results_20261031/RESULTS_REVIEW.md)、[独立复审](../outputs/private_workload_results_20261031/independent_review.md)。

'''+nxt[end:]
 marker='## 当前行动建议';nxt=nxt[:nxt.index(marker)]+'''## 当前行动建议

私有工作负载探索已完成；下一项推荐第2项独立性能确认。冻结完整与2048代表设置，保留1024反例；平衡顺序、独立进程、重复计时，区分机器噪声与训练实例差异。正式协议在写代码前确定，本次没有自动启动。

主贡献仍是整体计算省算，质量按原≤1个百分点护栏判断而非要求提高ACC。强非IID2048有一个seed越界必须披露；不能通过平均种子或事后放宽护栏称为全部通过。随后再推进第二数据集、K/规模和数值专项；静态选路复核继续暂缓。
'''
 put('docs/NEXT_EXPERIMENTS.md',nxt)
 put('docs/REPRODUCIBILITY.md',(base/'docs/REPRODUCIBILITY.md').read_text(encoding='utf-8')+'''
## 私有头部工作负载：正式完成

运行：`python -m experiments.private_workload.run --preset full --prepare-device cuda --download --memory-audit`；中断恢复加`--resume`，仅复用完整case，非轮中优化器恢复。

18个原始case和大summary无损归档于archives/private_workload_*.zip，解压到原路径后completed.json核验51文件；小报表/内存档案直接保留。数据集和特征缓存不上传；异机重新准备并使用新输出。精确历史full锚校验还需public_budget对应六个原始case。主审脚本需要原环境缓存；审计不是独立重训。正式本地run.py/test_workload.py已补直方图、依赖源码冻结和私有账本检查，随本次上传，核心训练源码未改；历史云端VALIDATION.md仅是开发阶段记录。

正式51文件哈希、18case、18内存档案、8份报表逐字节重生成和3600轮×方法历史锚点一致。原始计时离群未剔除，没有将此前已确认暂停移植到本实验。内存回放仅完整档，其耗时不作为性能证据。质量预算护栏：2048 5/6，1024 0/6；同预算B/E/D学习轨迹一致。详见outputs/private_workload_results_20261031。
''')
 expected=[];packets=[];batch=[];size=0;blobs=[]
 for p in sorted(STAGE.rglob('*')):
  if not p.is_file():continue
  b=p.read_bytes();rel=p.relative_to(STAGE).as_posix();expected.append(dict(path=rel,sha=blob(b)))
  if p.suffix=='.zip':blobs.append(dict(kind='blob',path=rel,encoding='base64',content=base64.b64encode(b).decode()))
  else:
   item=dict(path=rel,mode='100644',type='blob',content=b.decode('utf-8'));n=len(json.dumps(item))
   if batch and size+n>80000:packets.append(dict(kind='tree',entries=batch));batch=[];size=0
   batch.append(item);size+=n
 if batch:packets.append(dict(kind='tree',entries=batch))
 packets+=blobs;t=HERE/'transport';t.mkdir(exist_ok=True);index=[]
 for i,item in enumerate(packets):
  data=json.dumps(item,ensure_ascii=True,separators=(',',':'));(t/f'{i}.json').write_text(data,encoding='ascii');index.append(dict(index=i,kind=item['kind'],chars=len(data)))
 (HERE/'transport_index.json').write_text(json.dumps(index),encoding='utf-8');(HERE/'expected.json').write_text(json.dumps(expected),encoding='utf-8')
 print(json.dumps(dict(files=len(expected),archives=len(archives),zip_bytes=sum(x['bytes'] for x in archives),packets=index)))
if __name__=='__main__':main()
