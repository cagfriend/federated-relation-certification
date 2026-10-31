"""Resource review from paired, pause-excluded timing; raw experiment is immutable."""
import json
from pathlib import Path
HERE=Path(__file__).parent
def main():
    a=json.loads((HERE/'audit.json').read_text());assert a['manual_pause_exclusion']['not_fault_events']
    def cost(p,c,b):return next(r for r in a['cost_summary'] if (r['partition'],r['case_id'],r['comparison'])==(p,c,b))
    lines=['# 固定公共预算实验：正式结果审核','',
    '日期：2026-10-31。18组、54条B/E/D真实训练及18次隔离内存回放完成。用户确认两段长区间均为手动暂停；按要求排除性能计时，不计入故障。未修改实验源码、原始记录或训练质量结果。','',
    '## 暂停排除及配对公平性','',
    '- 已确认事件：IID seed404 M16384 fixed8的E第119轮；强非IID seed404 M16384 fixed8的B第100轮。',
    '- 共同掩码：IID seed404统一从全部3配置及B/E/D计时剔除r119，强非IID seed404统一剔除r100。对应配置每方法计199轮，其他seed计200轮；共排除18条方法轮计时，保证同预算算法比较和同M预算比较使用相同轮集合。',
    '- 方法初始化、C0和载入保留一次；没有估算暂停长度或用中位数替换时间。训练/参数/目标/质量/覆盖/工作量及内存仍按实际完整200轮保存，暂停不是故障或失败轮。',
    '- 51份原始文件和completed.json保持原样。主要性能统计以本报告、audit.json及pause_adjusted/为准；原始未过滤报表与audit_raw.json仅供追溯。','',
    '## 实现及完整性验收','',
    '实验固定Fashion-MNIST、IID/容量约束Dirichlet α0.1、seed404/505/606、六客户端宽度512×3/2048×3、冻结AE、私有总43616张、degree1、K10、200轮。三规格为M4096 full8、M16384 full32、M16384 fixed8。固定预算只让学生读取随机排列前2048边；教师生成、聚合、交换和oracle仍覆盖整个约定图。','',
    '51文件哈希和新实验/公共核心/准备源码匹配；18case、6缓存、18memory验证通过；398131200次关系与530841600次候选检查零不一致，3600历史锚对照一致。八份原始报表逐字节重生成，另生成公开掩码下的八份派生报告及摘要。旧非IID/机制86份结果不变。','',
    '同配置B/E/D逐轮参数、接收目标、损失、消息和评估严格一致。时间过滤不回滚训练；预算缩减的质量变化不是认证误差。轮数和边数不充作独立性能样本，独立seed仍为3。','',
    '## 认证省算：排除暂停后的主统计','',
    '以下同配置/seed先算D/基线，再取三个seed中位；百分比为耗时减少，负数表示D较慢。','',
    '|划分|配置|D/B生成减少|D/B完整头减少|D/B C0＋头减少|D/E完整头减少|D/E头胜出|','|---|---|---:|---:|---:|---:|---:|']
    for p in ('iid','dirichlet_0.1'):
        for cid in ('m4096_full','m16384_full','m16384_fixed8'):
            b,e=cost(p,cid,'D/B'),cost(p,cid,'D/E')
            vals=[b['generation_seconds_ratio'],b['head_pipeline_seconds_ratio'],b['with_shared_preparation_seconds_ratio'],e['head_pipeline_seconds_ratio']]
            lines.append('|'+p+'|'+cid+'|'+'|'.join(f'{100*(1-v):.2f}%' for v in vals)+f"|{e['head_wins']}/3|")
    for p,label in [('iid','IID'),('dirichlet_0.1','强非IID')]:
        b,e=cost(p,'m16384_fixed8','D/B'),cost(p,'m16384_fixed8','D/E')
        lines+=['',f"{label}大M固定8步：D/B完整头省时{100*(1-b['head_pipeline_seconds_ratio']):.2f}%、{b['head_pipeline_seconds_saved_seconds']:.2f}秒；含准备省时{100*(1-b['with_shared_preparation_seconds_ratio']):.2f}%。D/E头部省时{100*(1-e['head_pipeline_seconds_ratio']):.2f}%、{e['head_pipeline_seconds_saved_seconds']:.2f}秒，{e['head_wins']}/3胜出。"]
    lines+=['','D/B头部18/18较快；D/E生成18/18较快，但头部仅11/18较快。提高生成工作占比后相对B的整体收益扩大，但不能将它替代相对E的增量价值；IID相对E的反向结果在排除暂停后仍存在。两个手动暂停不再用于性能统计或故障解释。','',
    'B生成占比中位：IID约8.17%→16.34%→26.13%，强非IID约7.79%→15.17%→24.82%（依次小M full、大M full、大M fixed8）。大M fixed8 D真实刷新比例约IID7.94%、强非IID10.34%，E约13.41%/16.65%；刷新统计保留实际完整200轮。','',
    '## 预算缩减效果和质量护栏','',
    '同M16384公共更新由每客户端32步降到8步，实际六客户端200轮优化步数38400→9600，减少75%。该实际工作量不因计时掩码改写；预算效果计时用同一保留轮集合。减少预算的收益与D认证贡献分列。']
    for p,label in [('iid','IID'),('dirichlet_0.1','强非IID')]:
        r=next(r for r in a['budget_effects'] if r['partition']==p and r['method']=='D')
        lines+=['',f"{label}同方法D的fixed/full头部比中位{r['head_fixed_over_full_median']:.4f}，约省{100*(1-r['head_fixed_over_full_median']):.2f}%、{r['head_seconds_saved_median']:.2f}秒；含准备成本比{r['with_preparation_fixed_over_full_median']:.4f}。"]
    lines+=['','同M fixed8相对full最终平均ACC差中位IID−0.0317个百分点、强非IID−0.2650个百分点；最大平均下降0.4967个百分点，6/6通过预设≤1个百分点护栏。个别客户端最多下降1.79个百分点，平均护栏不等于逐客户端保证。NMI/ARI、两方法各自最差差及同client最小差另列，不要求准确率提高。','',
    '所有大M fixed配置完整200轮后每客户端累计覆盖全部边和端点；每轮只采25%边不等于永久忽略其余边。','',
    '## 内存与通信代价','',
    '大M D比B持久方法数组多25.35 MiB，小M多6.78 MiB；D与E相同。隔离进程峰值D/B约多21.1%、272.8 MiB，D/E基本相同。峰值包括共同特征、进程基础及临时数组，不由持久数组直接替代；不测AE准备峰值/GPU显存，内存回放耗时不参与性能统计。','',
    '同配置B/E/D字节相同；固定学生预算仍交换完整图目标，认证无新增通信压缩。头部秒表含初始化、私有更新、教师生成、交换、公共SGD；oracle/覆盖观察/评估在外。C0完整计最大公共池准备及载入，不摊薄、不因缓存复用记零，也不代表每个M的最小部署准备成本。串行六客户端之和不是并行轮时延。','',
    '## 结论范围与后续','',
    '第3.1第一阶段完成，私有工作负载尚未减小。大M fixed8是有利计算场景候选；相对E仍有场景边界。用户确认的手动暂停已剔除，不再当未知系统故障，也不据它要求重做全实验。若需独立性能确认，另冻结配置安排预定重复/隔离进程测时；当前三个既有seed仍为探索。准确率只作容忍护栏，协作优于Local/Self不是前提，静态选路复核仍暂缓。','',
    '独立复审GPT-6 Luna/high直接核对51哈希、18 raw case成本/质量、18内存及暂停记录；用户说明后按共同掩码从raw round_records独立重算。主审另执行完整case/profile/cache校验、八份原始报表重生成和旧86结果检查，复核独立算术一致。通过完整性、同配置精确性与平均ACC护栏；成本按公开排除规则接受为探索性配对证据，不扩大成D/E普遍加速或新增通信收益。','',
    '证据：[主要审计](audit.json)、[暂停排除规则](PAUSE_EXCLUSION.json)、[排除轮次](excluded_round_timings.csv)、[保留轮数](retained_timing_rounds.csv)、[主要派生报告](pause_adjusted/report.md)、[重算脚本](adjust_pauses.py)、[独立复算](independent_calculations.json)、[独立复审](INDEPENDENT_REVIEW.md)。原始未过滤文件及audit_raw.json仅供追溯，不作为当前主性能统计。']
    (HERE/'RESULTS_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print('Adjusted review written')
if __name__=='__main__':main()
