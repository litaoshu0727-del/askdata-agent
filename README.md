# AskData Text2SQL Demo

本项目演示从自然语言 Query 到 SQL 生成与执行的端到端流程。

> **关于来源**
>
> 基线代码（Schema 索引、两阶段检索、CoT 规划、SQL 生成、MCP 路由、长短期记忆）
> 来自公开分享的 AskData 项目压缩包，版权归原作者所有，本仓库仅用于学习与二次开发。
>
> 本仓库在其上新增：macOS 环境适配、供应商解耦与 DeepSeek 接入、
> 本地 bge 向量与精排、11 表 81 字段的电商数据集、指代消解与多轮追问、
> 静默降级告警与回归测试。详见 [docs/排查记录.md](docs/排查记录.md)。

## 核心模块

```text
schema_indexing/      # Schema索引构建，离线阶段
schema_retrieval/     # Schema检索与SchemaGraph构建
cot_planning/         # CoT四元组规划
sql_generation/       # SQL生成
mcp_router/           # MCP路由执行
askdata_pipeline/     # 端到端流程编排
askdata_memory/       # 长短期记忆、个人知识库召回与会话编排
```

## 端到端运行

```bash
python -m askdata_pipeline.end_to_end_demo
```

当前 Demo 会自动创建 SQLite 测试库：

```text
runtime_data/trade_demo.db
```

测试 Query：

```text
查询总交易笔数大于50000的利率是多少
```

## 当前链路

```text
用户Query
  ↓
关键词抽取
  ↓
Schema混合检索 + RRF + Rerank
  ↓
SchemaGraph
  ↓
CoT四元组规划
  ↓
SQL生成
  ↓
MCP路由执行
  ↓
查询结果
```

动态路由会先结合长短期记忆判断用户意图：需要新业务数据时进入上述 Text2SQL 链路；结果解释、指标说明、历史结果追问和业务知识问答进入 `data_qa` 链路，不执行数据库查询。

路由实现位于 `askdata_pipeline/routing.py`，统一编排入口位于 `askdata_pipeline/dynamic_service.py`，对话问答实现位于 `askdata_pipeline/data_qa.py`。

暂不包含结果校验与回调修正。

## 长短期记忆

项目已支持滑动窗口、异步增量摘要、用户主动长期记忆存储，以及可选个人知识库召回。详细设计与调用方式见 [askdata_memory/README.md](askdata_memory/README.md)。

运行长短期记忆端到端 Demo：

```bash
python askdata_pipeline/memory_end_to_end_demo.py
```

## 大模型供应商配置

原先阿里云百炼的接口地址、模型名和 `DASHSCOPE_API_KEY` 散落在 4 个 Client 里，
现已收敛到 `llm_config.py`，按以下优先级自动解析：

```text
DEEPSEEK_API_KEY  >  DASHSCOPE_API_KEY  >  都没有（各 Client 自动降级到 Mock）
```

### 用 DeepSeek 跑通全链路

DeepSeek 只提供 Chat 接口，没有 Embedding、也没有 Rerank 服务，
所以链路上的 5 个模型调用点拆成两半：

| 调用点 | 走哪里 | 说明 |
|---|---|---|
| 关键词抽取 | DeepSeek | OpenAI 兼容格式，零改造 |
| CoT 四元组规划 | DeepSeek | 开启 thinking 模式 |
| SQL 生成 | DeepSeek | 关闭 thinking 模式 |
| 向量 Embedding | 本地 `BAAI/bge-small-zh-v1.5` | 约 95MB，512 维 |
| Rerank 精排 | 本地 `BAAI/bge-reranker-base` | 约 1.1GB，Cross-Encoder |

```bash
export DEEPSEEK_API_KEY="你的 DeepSeek APIKey"
export ASKDATA_LOCAL_MODELS=1

python -m askdata_pipeline.end_to_end_demo
```

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | — | DeepSeek API Key，设置后优先于阿里云 |
| `DEEPSEEK_CHAT_URL` | `https://api.deepseek.com/chat/completions` | Chat 接口地址 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 另一个可选值：`deepseek-v4-pro` |
| `DASHSCOPE_API_KEY` | — | 阿里云百炼 API Key |
| `DASHSCOPE_CHAT_URL` | 百炼 OpenAI 兼容地址 | Chat 接口地址 |
| `DASHSCOPE_CHAT_MODEL` | `qwen-plus` | 百炼模型名 |
| `ASKDATA_LOCAL_MODELS` | 关闭 | 设为 `1` 启用本地 bge 向量与精排 |
| `ASKDATA_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 本地向量模型 |
| `ASKDATA_RERANK_MODEL` | `BAAI/bge-reranker-base` | 本地精排模型 |
| `ASKDATA_DEVICE` | 自动 | 推理设备，例如 `mps` / `cpu` |

### 用 .env 保存配置

不想每开一个终端就 `export` 一遍，可以写进 `.env`：

```bash
cp .env.example .env
# 然后编辑 .env，把 DEEPSEEK_API_KEY= 后面填上你的 Key
```

`llm_config.py` 启动时自动读取，无需额外依赖。
优先级是 **命令行 export > .env > 代码默认值**，所以临时想换模型直接 export 覆盖即可。
`.env` 已写进 `.gitignore`，不会被提交。

### 关于 thinking 模式

DeepSeek 默认开启思考模式，而**思考模式下 `temperature` 参数会被忽略**。
项目按场景分别处理：

- CoT 四元组规划：显式开启思考（`thinking.type = enabled`），这本来就是推理场景
- SQL 生成、关键词抽取：显式关闭思考，让 `temperature=0.0` 真正生效，保证输出确定性

### 不配置任何 Key 时

行为与改造前完全一致：CoT 与 SQL 走 Mock，向量用本地哈希伪向量，精排用规则排序。
Demo 秒开，不下载任何模型。

## 电商数据集

原始的 `trade` 数据集只有 2 张表 9 个字段，随便召回几个字段就全命中了，
两阶段检索这套机制其实没派上用场。`ecommerce` 数据集用来补这一课。

### 规模

| 分层 | 表 | 说明 |
|---|---|---|
| dim | `dim_user` `dim_shop` `dim_product` `dim_category` | 用户、店铺、商品、类目 |
| fact | `fact_order` `fact_order_item` `fact_payment` `fact_refund` `fact_user_behavior` | 订单、明细、支付、退款、行为 |
| dws | `dws_user_summary` `dws_shop_daily` | 用户累计指标、店铺日报 |

合计 11 张表、81 个字段、约 7000 行数据，固定随机种子生成，每次结果一致。
dws 汇总层由事实表聚合而来，`SUM(dws_shop_daily.gmv)` 与 `SUM(fact_order.order_amount)` 严格相等。

### 刻意埋的坑

这套 Schema 专门设计了几组近义字段，用来检验检索的区分能力：

- **9 个金额字段**：`order_amount`（订单原价）、`pay_amount`（实付）、`discount_amount`（优惠）、
  `freight_amount`（运费）、`refund_amount`（退款）、`item_amount`（明细）、
  `gmv`（成交总额）、`total_pay_amount`（累计实付）、`avg_order_amount`（客单价）
- **`pay_amount` 在两张表里都有**：`fact_order` 里是订单实付，`fact_payment` 里是支付流水
- **`city` 在两张表里都有**：`dim_user.city` 是买家所在地，`dim_shop.city` 是店铺经营地
- **`finish_time` 在两张表里都有**：订单里是确认收货，退款里是退款到账
- **纯业务口径词**：用户说“客单价”“销售额”，字段名叫 `avg_order_amount`、`gmv`，字面零重合

### 运行

```bash
python -m askdata_pipeline.ecommerce_demo
python -m askdata_pipeline.ecommerce_demo --query "客单价最高的10个用户是谁"
```

在代码里切换数据集：

```python
PipelineConfig(dataset="ecommerce", database_name="ecommerce_db", db_path=...)
```

### 检索参数要随 Schema 规模放大

`rerank_top_n = 关键词数 × rerank_top_multiplier`。默认的 multiplier=2 对 9 个字段的
trade 库够用，但在 81 个字段上，2 个关键词只保留 4 个字段，必然漏召回。
`text2sql_pipeline._build_retrieval_config()` 里按数据集分开配置：
ecommerce 用 multiplier=6、min_top_n=10、max_top_n=30、RRF final_top_k=60。

**这是把 Demo 搬到真实库时最容易踩的坑**——链路没报错，只是悄悄少给了几个字段，
表现为模型说“Schema 里没有这个字段”。

### 换成你自己的库

照着 [ecommerce_data.py](askdata_pipeline/ecommerce_data.py) 改三处：

1. `sql/create_*.sql` 换成你的建表语句，**外键一定要声明**，表关系是靠它自动提取的
2. `get_*_business_meta()` 写字段的业务含义和别名——这份元数据的质量直接决定召回准确率
3. `_prepare_dataset()` 里加一个分支

元数据里最值钱的是 `aliases` 和近义字段的辨析：把业务口头怎么说、这个字段和那个字段差在哪
写清楚，检索准确率的提升比换更大的模型明显得多。

## 静默降级告警

这个项目最难发现的不是报错，是「链路跑通、退出码 0、输出看着合理，
但中间某一环已经悄悄失效了」。三个真实案例见 [docs/排查记录.md](docs/排查记录.md)。

[askdata_diagnostics.py](askdata_diagnostics.py) 给每一处已知的降级点装了探针：
出问题时要么在 stderr 留下一行告警，要么被 `PipelineResult.diagnostics` 带出来。

### 降级码

| Code | 含义 | 后果 |
|---|---|---|
| `COT_PARSE_EMPTY` | CoT 有输出但没解析出四元组 | **一条 SQL 都不会生成**，链路安静停住 |
| `SCHEMA_RECALL_CAPPED` | 精排名额相对候选数过小 | 可能已截掉需要的字段，模型会说「Schema 里没这个字段」 |
| `MODEL_MOCK_FALLBACK` | 没 Key，CoT / SQL 走写死的 Mock | 换任何非内置 Query 都会返回缺失或 `SELECT 1` |
| `RERANK_MOCK_FALLBACK` | 没 Rerank 服务，精排走规则排序 | 只覆盖内置词表，没有通用语义判断 |
| `EMBEDDING_MOCK_FALLBACK` | 向量是哈希伪向量 | 语义召回实际失效，只剩字面匹配 |
| `COLUMN_SAMPLES_FAILED` | 字段样例值抽取失败 | 索引文本少一块语义，召回质量下降 |

### 怎么看

Demo 会在最后集中展示：

```text
9. 本次运行的降级记录
共 4 条。结果看着正常，但以下环节实际已经打了折扣：

  ⚠️  [EMBEDDING_MOCK_FALLBACK] 当前使用本地哈希伪向量，没有真实语义能力……
  ⚠️  [MODEL_MOCK_FALLBACK] 未配置 API Key，CoT 规划降级为写死的 Mock 结果……
```

配好 DeepSeek + 本地 bge 之后应该是：

```text
【6】降级记录
    无降级，链路每一环都在满配置下跑完
```

代码里读：

```python
result = pipeline.run(query)

if result.diagnostics:
    for item in result.diagnostics:
        print(item.render())
```

自己的代码里收集：

```python
from askdata_diagnostics import collect

with collect() as diagnostics:
    ...  # 跑链路
```

`collect()` 基于 `contextvars`，只覆盖当前执行上下文。
后台线程（例如记忆模块的异步摘要）里的降级仍然会写 logging，但不进 `collect()` 列表。

### 回归守卫

[tests/test_diagnostics.py](tests/test_diagnostics.py) 里有两条测试直接对应排查记录里的问题：

- `test_punctuation_variants_all_parse` —— 锁死 CoT 四元组在句号、半角逗号、全角逗号、无标点四种写法下都能解析
- `test_narrow_config_emits_recall_capped` —— 把精排参数调回出事前的值，断言告警必须触发；
  当前参数下断言不触发

这两条保证同样的 bug 不会再悄悄回来。

## 多轮追问

单轮问答只考验 Text2SQL，多轮真正难的是**指代消解**：
用户第二句说「它们的退款金额呢」，「它们」指的是上一轮 SQL 查出来的那三家店铺——
这个信息不在当前 Query 里，只存在于会话记忆中。

```bash
python -m askdata_pipeline.multi_turn_demo
```

五轮对话覆盖四种典型形态：

| 轮次 | 问题 | 路由 | 查库 | 考点 |
|---|---|---|---|---|
| 1 | 销售额最高的三个店铺是哪些 | `database_query` | 是 | 基线，纯 Text2SQL |
| 2 | 它们的退款金额分别是多少 | `database_query` | 是 | 指代消解 + 新数据需求 |
| 3 | 刚才第一名的店铺叫什么名字 | `data_qa` | 否 | 复用历史结果，不打数据库 |
| 4 | 客单价这个指标是怎么算的 | `data_qa` | 否 | 指标口径问答 |
| 5 | 帮我查一下这些店铺的买家数 | `database_query` | 是 | 指代对象已滑出短期窗口 |

### 指代消解是独立的一步

把会话记忆拼在 Query 前面一起送进 CoT，指望模型顺手解决——实测不行，两种失败都会出现：

- **关键词抽取拿到的是原始 Query**，把「它们」当成了检索词，真正的指代对象根本没进检索
- **CoT 看到了上下文但没被要求先解指代**，结果要么忽略限定条件查了全表，
  要么从店铺名「臻品自营店15」里抠出数字 15 当成 `shop_id`，凭空造出一个过滤条件

所以 [query_rewriter.py](askdata_pipeline/query_rewriter.py) 把它拆成显式的一步，
放在关键词抽取**之前**：

```text
用户：它们的退款金额分别是多少
  ↓ 指代消解
销售额最高的三个店铺"臻品自营店15""优选旗舰店1""旗舰旗舰店7"的退款金额分别是多少
  ↓ 关键词抽取
销售额，店铺，臻品自营店15，优选旗舰店1，旗舰旗舰店7，退款金额
  ↓ SQL
WHERE dim_shop.shop_name IN ('臻品自营店15', '优选旗舰店1', '旗舰旗舰店7')
```

改写 Prompt 里有一条专门约束：**绝对不要凭空推断任何 ID**。
店铺名叫「臻品自营店15」不代表它的 ID 是 15——这是实测中模型真实犯过的错。

只有检测到指代词（它们、这些、刚才、上述……）才会调模型，自包含的问题直接短路，
不浪费一次调用。

### 指标口径问答要看得见 Schema

`data_qa` 原本只拿得到会话记忆，问「客单价怎么算的」只能回答「上下文里没有定义」。
但 `dws_user_summary.avg_order_amount` 的元数据里明明写着「业务上叫客单价」。

`build_metric_glossary()` 把 `business_meta` 压成一份指标口径表喂给 `data_qa`，
现在能直接定位到表名、字段名和业务含义。

### 相关降级码

| Code | 触发条件 |
|---|---|
| `QUERY_REWRITE_SKIPPED` | 检测到指代词但没 Key，多轮追问结果大概率不正确 |
| `QUERY_REWRITE_FAILED` | 指代消解调用失败，已回退为原始 Query |
| `EMPTY_RESULT_SET` | SQL 执行成功但返回 0 行，筛选条件可能有问题 |

`EMPTY_RESULT_SET` 就是为幻觉 ID 这类问题准备的——
`WHERE shop_id IN (15, 1, 7)` 不会报错，只会安静地返回 0 行。

## 评测

```bash
python -m eval.runner                  # 跑全部 50 题
python -m eval.runner --case E36       # 只跑一道
python -m eval.runner --tag 嵌套聚合    # 只跑某类考点
```

### 为什么需要它

在有评测集之前，每次改动都是「跑一条 Query 看对不对」。这带来两个问题：

- **没法回答"提升了多少"。**元数据写得再细，也只能说「感觉准了」。
- **bug 是撞见的，不是测出来的。**曾经有一个 SQL 表名前缀的 bug，
  同一道题连过两轮、第三轮才挂——手跑单条 Query 有 2/3 的概率看不见它。

### 三个指标分开统计

| 指标 | 衡量什么 | 定位到 |
|---|---|---|
| Schema 召回率 | 该命中的字段有没有被召回 | 检索环节 |
| 执行准确率 | 结果集与参考答案是否一致 | 生成环节 |
| 陷阱题诚实率 | Schema 支撑不了时会不会编 | 可靠性 |
| 端到端准确率 | 整条链路 | 总分 |

召回 92% 但端到端 61%，说明问题在 CoT 或 SQL 生成；两个都低，说明元数据没写好。
**一个总分只能告诉你「不行」，分指标才能告诉你「哪不行」。**

### 判分方式

**不比 SQL 字符串，比执行结果。**同一个问题有无数种正确写法
（JOIN 条件左右互换、列别名不同、子查询 vs JOIN），比字符串没有意义。
比对时只看**值**不看列名，行内值排序、行间集合比对，
这样容忍列别名和排序差异，但抓得住值错、行数错、筛选条件错。

两条从踩坑里学到的规矩：

- **`must_hit_columns` 支持候选组。**同一个问题常有多条正确路径——
  「某天的订单量」既能数 `fact_order.create_time`，也能用
  `dws_shop_daily.stat_date`。只认一条路径，测的就不是系统而是出题人的预设。
- **题目措辞必须让输出列无歧义。**问「客单价最高的10个用户的客单价是多少」，
  模型多返回一列 `user_id` 不能算错。输出不明确的题目没法客观判分。

### 题库构成

50 题，21 类考点：

| 组 | 题号 | 考点 |
|---|---|---|
| A | E01–E22 | 基础覆盖：单表过滤、分组统计、金额字段辨析、枚举值匹配 |
| B | E23–E32 | 跨表多跳：2–3 次 JOIN、层级类目、同名字段消歧 |
| C | E33–E40 | 嵌套聚合：子查询、两个聚合相除、比率计算 |
| D | E41–E45 | 时间窗口：区间、按天分组、上下旬对比 |
| E | E46–E50 | 陷阱题：Schema 根本支撑不了，考的是会不会编 |

陷阱题（手机号、库存、员工数、物流时效、精确年龄）是刻意设计的——
**能诚实说「我没有这个数据」的系统，比什么都敢答的系统可靠得多**，
而这一点不专门测就永远不知道。

### 单次运行有误差，用 --repeat 压掉

同一份代码、同一份题目跑两次，50 题里有 **5 题结果不一样**：

```text
E18  第一次 ✅ → 第二次 ❌        E28  第一次 ❌ → 第二次 ✅
E24  第一次 ✅ → 第二次 ❌        E39  第一次 ❌ → 第二次 ✅
E38  第一次 ✅ → 第二次 ❌
```

源头是关键词抽取本身非确定：模型这次吐「直播间」、下次吐「渠道」，
一路级联到召回、精排和最终 SQL。单次运行因此带着约 ±5% 的误差棒。

**这意味着单次跑出来的前后对比基本是在噪声里找信号。**

```bash
python -m eval.runner --repeat 3
```

重复模式下：

- 每题按**多数**判定通过，展示 `2/3`、`0/3` 这样的通过次数
- 输出单次运行分布和波动幅度：`40/50　38/50　41/50　→　76% ~ 82%，波动 3 题`
- 单列**抖动题**（同一份代码结果不一致的那些）

抖动题本身就是脆弱信号：它说明这道题的链路某一环依赖了模型的随机输出，
比稳定失败的题更值得先看——稳定失败是能力问题，抖动是鲁棒性问题。

### 熔断：宁可没有数字，也不要假数字

一次 150 运行的评测跑到一半断网，后面 26 题全部 0.0 秒失败，重试机制空转 162 次，
最后仍然吐出一份**格式完整的报告**：

```text
端到端准确率     21/50    42%
陷阱题诚实率      0/5      0%
单次运行分布　21/50　21/50　21/50　→　42% ~ 42%，波动 0 题
```

每个数字都是假的。那句"波动 0 题"看着像好消息，其实是故障的指纹——
真正的随机抖动不可能三次完全一致。

如果不逐题去看耗时，很容易把 42% 当成真实退步，然后去修一个根本不存在的问题。
**一个会输出无效数字的评测器，比没有评测器更危险。**

现在评测器会：

1. **区分故障类型。**DNS 失败、Key 失效、余额耗尽属于持续性故障，**不重试**——
   重试一百次也是一样的结果，只会白烧时间掩盖问题。超时、限流才值得重试。
2. **连续 3 次基础设施故障就中止**（`--abort-after` 可调），退出码 2。
3. **中止时一个百分比都不输出。**半截数据算出来的准确率没有意义，
   而一旦印成百分数就会被当成结论。

```text
⛔ 评测未完成，不输出指标
  中止原因　连续 3 次基础设施故障
  故障类型　persistent
  完成进度　23/50 题

  半截数据算出来的准确率没有意义，因此这里不给任何百分比。
  请先排查环境（网络 / DNS / API Key / 余额 / 限流），再重跑。
```

注意 SQL 报错、结果不符这类**系统真实失败**不计入熔断计数，只有环境故障才算。
