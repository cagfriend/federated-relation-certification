# 实现定位、优化归属与资源边界

运行 D 由[生成入口](../../experiments/public_scaling/generation.py)选择[偏置净变化](../../experiments/public_scaling/endpoint_bias.py)。下表列出其复用的底层操作。

|部件|当前实现与目的|代码|
|---|---|---|
|冻结表示|预训练后缓存特征，头部实验不反传编码器|[准备与引擎](../../experiments/public_scaling/engine.py)|
|候选缓存|赢家、分差、范数、类对累计前缀及样本参考行|[RelationGenerator](../../experiments/public_scaling/certification.py)|
|关系级认证|uint64位集合交集判断，不确定端点布尔标记后去重|[generate](../../experiments/public_scaling/certification.py)|
|逐样本对照E|非单例样本全部重算，不额外承担关系位集合判断|[point分支](../../experiments/public_scaling/certification.py)|
|完整对照B|每样本打分一次，再查边；不是每条边重跑网络|[full分支](../../experiments/public_scaling/certification.py)|
|通信编码|实际位打包、full/delta/empty选择及严格解码|[codec](../../experiments/public_scaling/codec.py)|
|提交协议|保留每客户端关系，暂存计数、校验与推进版本|[protocol](../../experiments/public_scaling/protocol.py)|
|公共学生计算|batch内唯一端点，新鲜softmax、解析双端梯度|[head](../../experiments/public_scaling/head.py)|
|固定公共预算|图生成不减量，限制学生消费batch数|[public_budget](../../experiments/public_budget/README.md)|
|私有头工作量|独立随机流按客户端/轮抽样，三方法一致|[private_workload](../../experiments/private_workload/README.md)|

## 已有机制与未实施优化

类对累计前缀避免保存完整参数历史；候选位集合减少逐边集合运算开销；端点去重避免同一生成步骤重复教师打分。它们都是当前实现组成，不能每一项都宣称有独立因果消融证明。

当前公共核心`_advance`仍构造完整`K×K×d`增量数组。分块类对预算、压缩缓存或更换位集合布局可作为工程候选，不能因旧讨论中提过就说已全部落地。已有成本诊断和路径选择实验研究维护成本与策略选择，不等于每项底层优化已单独验证。

内存持久项约含`O(MK)`样本缓存与`O(K²)`前缀；临时类对数组可达`O(K²d)`。D与E通常持有相同认证缓存，而B不需要。报告应同时区分持久数组、进程峰值和准备缓存，不能称计算省时同时就节省内存。

## 测量口径

- 生成阶段：包括认证维护、必要打分和关系确定；不要只计矩阵乘法。
- 完整头部：含初始化以及私有更新、教师生成、协议、公共更新等被记录阶段；oracle与评估另计。
- 含准备：编码器、特征、KMeans及加载按原协议计入，不按方法数摊薄。
- 单方法隔离内存回放用于空间，不替代正式性能计时。
- 串行客户端耗时与内存消息处理，不是实际并行FL轮时延，也不是能耗。

每轮oracle在计时外核对关系、候选包含、计数、目标和参数摘要；大量边检查不能替代独立随机种子或计时重复。精确保持使D不会额外改变B的训练轨迹，但无法修复B自身的目标退化。

历史入口是否仍存在源码，以[代码台账](../evidence/CODE_HISTORY.md)为准；旧README中的运行命令仅供历史追溯。冻结源码本次没有迁移、重构或增加测试。
