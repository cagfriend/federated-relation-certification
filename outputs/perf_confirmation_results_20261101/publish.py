import json,hashlib,zipfile,base64,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[2];H=Path(__file__).parent;S=H/'stage';O=R/'experiments/perf_confirmation/results_full'
def put(rel,text):
 p=S/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
def cp(p):
 q=S/p.relative_to(R);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
S.mkdir(exist_ok=True)
section='''正式完成72次单方法独立进程运行：新seed707/808/909、每方法两次技术重复、IID与强非IID、完整和2048两档。重复先平均，seed为统计单位；12组非计时轨迹一致，零误差。

|划分|2048 D/B头部省时|2048 D/E头部省时|D/B含准备省时|D/E含准备省时|seed胜出D/B、D/E|
|---|---:|---:|---:|---:|---|
|IID|24.28%|5.73%|16.44%|3.60%|3/3、3/3|
|强非IID|24.09%|8.05%|16.08%|5.03%|3/3、3/3|

两划分均通过预注册C1（D/B中位≤0.90）、C2（D/E中位<1）和C3（seed胜出各≥2/3）。绝对省秒中位IID对B17.53秒、对E3.32秒；强非IID17.87秒、4.93秒。完整档也全部seed快于B/E，但IID完整档D/E省时中位仅1.09%。本次支持冻结配置下的计算收益，不能外推到所有模型、数据集和并行系统。

2048相对完整档的平均ACC下降，IID三个seed为0.42/0.37/0.35个百分点，强非IID0.46/0.33/0.20个百分点，6/6通过≤1个百分点护栏。同配置B/E/D轨迹与指标相同，预算缩减本身的收益不算认证贡献。既有探索实验强非IID2048的seed404越界和1024失败仍保留，不因本轮通过而撤销。

重复耗时相对差中位1.85%，最大61.05%；保留全部200轮与全部运行，不作离群剔除，不将未确认波动称为休眠或故障。逐轮private/generation/public筛查未发现超过max(1秒,10倍同轨迹阶段中位)的孤立尖峰，这不排除持续系统负载变化；详见独立审阅。三seed只报范围，不称置信区间。

主审重新校验72个封印记录、全部环境/来源身份、12组轨迹和8份报表逐字节重生成。记录707788800次关系检查、943718400次候选检查零误差；未重训或独立重演全部教师前向。原completed清单只含顶层文件，本次audit.json另给72个runs的SHA256；原始文件不改。进程峰值与墙钟仅描述性，含审计评估的峰值不能替代之前关闭审计的隔离内存实验。
'''
(H/'RESULTS_REVIEW.md').write_text('# 独立性能确认：正式审核\n\n更新：2026-11-01。\n\n'+section,encoding='utf-8')
for p in (R/'experiments/perf_confirmation').iterdir():
 if p.is_file():cp(p)
for p in O.iterdir():
 if p.is_file():cp(p)
groups={}
for p in (O/'runs').glob('*.json'):
 key=p.stem.rsplit('_',2)[0];groups.setdefault(key,[]).append(p)
archives=[]
for key,paths in sorted(groups.items()):
 rel='archives/perf_confirmation_'+key+'.zip';p=S/rel;p.parent.mkdir(exist_ok=True);files=[]
 with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for src in sorted(paths):
   b=src.read_bytes();name=src.relative_to(R).as_posix();i=zipfile.ZipInfo(name,(2026,11,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;z.writestr(i,b,compresslevel=9);files.append(dict(path=name,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b)))
 with zipfile.ZipFile(p) as z:
  assert z.testzip() is None
  for src in paths:assert z.read(src.relative_to(R).as_posix())==src.read_bytes()
 archives.append(dict(archive=rel,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),files=files))
put('archives/ARCHIVE_MANIFEST.json',json.dumps(json.loads((H/'base/archives/ARCHIVE_MANIFEST.json').read_text(encoding='utf-8'))+archives,indent=2))
for name in ('audit.py','audit.json','RESULTS_REVIEW.md','INDEPENDENT_REVIEW.md','publish.py'):cp(H/name)
link='outputs/perf_confirmation_results_20261101/RESULTS_REVIEW.md'
readme=(H/'base/README.md').read_text(encoding='utf-8').replace('下一项推荐独立性能确认','独立性能确认已完成，下一项推荐第二数据场景验证')
put('README.md',readme+'\n## 新完成：独立性能确认（2026-11-01）\n\n'+section+f'\n[正式审核]({link}) · [独立复审](outputs/perf_confirmation_results_20261101/INDEPENDENT_REVIEW.md)\n')
put('docs/EXPERIMENTS.md',(H/'base/docs/EXPERIMENTS.md').read_text(encoding='utf-8')+'\n## 12. 独立性能确认\n\n'+section+f'\n[审核](../{link})\n')
n=(H/'base/docs/NEXT_EXPERIMENTS.md').read_text(encoding='utf-8');a=n.index('## 2.');b=n.index('## 3.',a)
n=n[:a]+'''## 2. 已完成：独立性能确认

2026-11-01：新seed707/808/909，两次技术重复，72次单方法独立进程，12组轨迹一致。2048档两划分均通过预注册C1/C2/C3。D/B完整头省时中位IID24.28%、强非IID24.09%；D/E省5.73%/8.05%。质量6/6通过≤1个百分点护栏。重复差中位1.85%、最大61.05%，全部保留，说明仍有运行噪声；不外推成任意环境性能保证。

不再将此确认列为待运行。下一项推荐第二数据场景与公共库分布验证，维持冻结表示、同家族异宽、固定公共预算，以整体计算省时和资源代价为主，质量作容忍护栏。静态选路复核继续暂缓。[正式审核](../outputs/perf_confirmation_results_20261101/RESULTS_REVIEW.md)。

'''+n[b:]
n=n.replace('|待安排，与静态选路复核分开|','|已完成72次独立进程，两划分均确认|')
n=n.replace('下一步只推荐第2项独立性能确认，2048是待确认候选，不是已普适最优。','第2项独立性能确认现已完成，2048在冻结场景中得到确认，仍非普适最优。')
if '## 当前行动建议' in n:n=n[:n.index('## 当前行动建议')]+'''## 当前行动建议

独立性能确认已完成。下一项建议第二数据集及公共样本分布验证，先冻结实验协议再编码；随后按瓶颈做K/规模、峰值内存与数值边界专项。主目标为整体计算优化，允许预设范围质量下降。保留历史不利配置及本次计时噪声，不重启暂缓的静态选路复核。本次没有启动新实验。
'''
put('docs/NEXT_EXPERIMENTS.md',n)
put('docs/REPRODUCIBILITY.md',(H/'base/docs/REPRODUCIBILITY.md').read_text(encoding='utf-8')+'''\n## 独立性能确认正式结果

72原始runs无损ZIP保存，路径见archives/ARCHIVE_MANIFEST.json；顶层结果直接可读。audit.json补充72个运行文件哈希。运行源码含本地补齐public_budget依赖冻结、全部72次完成后才发布判定的修正；预注册规则与训练引擎未改变。异机需要重新准备数据与使用新输出，绝对路径缓存不上传。原始环境仅可在源码完全一致时resume。\n''')
packets=[];expected=[]
for p in sorted(S.rglob('*')):
 if not p.is_file():continue
 b=p.read_bytes();rel=p.relative_to(S).as_posix();expected.append(dict(path=rel,sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()))
 packets.append(dict(kind='blob',path=rel,content=base64.b64encode(b).decode()) if p.suffix=='.zip' else dict(kind='tree',entries=[dict(path=rel,mode='100644',type='blob',content=b.decode('utf-8'))]))
t=H/'transport';t.mkdir(exist_ok=True);index=[]
for i,p in enumerate(packets):
 s=json.dumps(p,ensure_ascii=True);(t/f'{i}.json').write_text(s,encoding='ascii');index.append(dict(index=i,chars=len(s),kind=p['kind']))
(H/'index.json').write_text(json.dumps(index));(H/'expected.json').write_text(json.dumps(expected));print(json.dumps(dict(files=len(expected),archives=len(archives),zipbytes=sum(x['bytes'] for x in archives))))
