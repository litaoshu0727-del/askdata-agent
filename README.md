# AskData Text2SQL

[![tests](https://github.com/litaoshu0727-del/askdata-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/litaoshu0727-del/askdata-agent/actions/workflows/tests.yml)

自然语言问题 → Schema 检索 → CoT 规划 → SQL 生成 → 执行，一条可评测、出错会告警的
Text2SQL 链路。

> **来源**：基线代码（Schema 索引、两阶段检索、CoT 规划、SQL 生成、MCP 路由、长短期记忆）
> 来自公开分享的 AskData 项目压缩包，版权归原作者所有，本仓库仅用于学习与二次开发。
> 新增部分见下文；改动过程和每个数字的出处在 [docs/实验记录.md](docs/实验记录.md)。

## 结果

| 题库 | 是否照着它调过 | 端到端 | 首轮检索召回 |
|---|---|---|---|
| ecommerce 主题库　61 题 × 5 | 调过 | 60/61（唯一失败 E30 是判分问题，校正后 5/5） | 93/95 |
| Chinook 主题库　15 题 × 3 | 调过 | 15/15 | 18/18 |
| 留出集一　ecommerce 30 + Chinook 15 | 没有，已封存 | 29/30、15/15 | 74/74、26/31 |
| 留出集二　Chinook 20 | 没有，已用过 | 19/20 | 修精排前 88% → 修后 98% |
| 留出集三　ecommerce 30 + Chinook 20 | 没有，已用过 | 29/30、20/20 | 134/135 |
| [留出集四](docs/实验记录.md#第四套留出集四处改动在没见过的题上)　ecommerce 30 + Chinook 20 | 没有，已用过 | 29/30、20/20 | 345/351 |

陷阱题（库里根本没有这个数据）诚实率在所有题库上都是 100%。留出集由全新上下文的子代理
盲写，在第一次运行之前冻结提交（[协议](docs/实验记录.md#协议)）。留出集四是当前版本的成绩：
第三套之后的四处改动里，整数除法规则在陌生题上测出了收益，其余三处没有可帮的题、也没测出代价。

## 主要结论

1. **拒答要建立在完整信息上。**模型常把"我没看到这个字段"说成"库里没有"。拒答前用全量
   Schema 复核一次，端到端 82% → 90%，诚实率 80% → 100%
   （[详情](docs/实验记录.md#拒答必须建立在完整信息上)）
2. **元数据的收益先落在检索上。**Chinook 首轮召回 50% → 94%，ecommerce 端到端 +8 个点；
   能不能传导到准确率，取决于字段到齐之后题目还剩多少难度
   （[详情](docs/实验记录.md#真正的变量不是-schema-大小是题目难度)）
3. **手写的精排文本比自动生成的还差。**删掉之后，Chinook 留出集首轮召回 88% → 98%，
   ecommerce 留出集 6 道题变好、0 道变差
   （[详情](docs/实验记录.md#第二套留出集修-chinook-精排在没见过的题上验证)）
4. **分数涨了，先问是系统变了还是判分变了。**主题库 87% → 98% 的 11 个点里，大约一半是
   判分校正（[详情](docs/实验记录.md#这条线的账)）
5. **最危险的是零告警的错答案。**链路跑通、数字看着合理，中间某一环已经悄悄失效。
   降级告警和筛选值守卫都是为它做的（[详情](docs/实验记录.md#堵住零告警筛选值守卫)）
6. **两个机制做了但没有收益。**自洽性投票净效果为零、成本 2.7 倍，默认关闭；
   Schema 索引在当前规模下省不了时间，启动耗时的 98% 在加载模型
   （[投票](docs/实验记录.md#自洽性投票数学上有前提当前净效果为零)、
   [索引](docs/实验记录.md#先说清楚当前规模下没有性能收益)）

## 链路

```text
用户问题
  → 路由：要查新数据走 Text2SQL；结果解释、指标口径、历史追问走 data_qa，不查库
  → 指代消解（多轮追问时，"它们"改写成上一轮的具体对象）
  → 关键词抽取
  → Schema 混合检索：BM25 + 向量 → RRF（按关键词保底进池）→ 精排 → 关键词覆盖 → 时间约束保底
  → SchemaGraph（关键词落在的表之间不连通时，沿外键补桥接表）
  → CoT 四元组规划 ── 判"缺失"时用全量 Schema 复核一次
  → SQL 生成 → 执行 ── 报错时带报错回调修正
  → 筛选值守卫：问题提到的枚举取值 SQL 没用上，就带提示重规划
  → 结果 + 降级记录
```

| 目录 | 内容 |
|---|---|
| `schema_indexing/` | Schema 索引构建（离线） |
| `schema_retrieval/` | 混合检索、精排、SchemaGraph |
| `cot_planning/` | CoT 四元组规划 |
| `sql_generation/` | SQL 生成与修正 |
| `mcp_router/` | 路由与 SQLite 执行 |
| `askdata_pipeline/` | 端到端编排、路由、指代消解、筛选值守卫、数据集 |
| `askdata_memory/` | 长短期记忆（[说明](askdata_memory/README.md)） |
| `askdata_web/` | Web 界面 |
| `eval/` | 评测器与题库 |

相对基线的新增：DeepSeek 接入与本地 bge 向量 / 精排、电商与 Chinook 两个数据集、
指代消解、全量复核、筛选值守卫、时间约束保底、SQL 回调修正与自洽性投票、降级告警、
Web 界面、评测器与三套留出集。

## 快速开始

```bash
conda create -n askdata python=3.12 && conda activate askdata
pip install -r requirements.txt
cp .env.example .env        # 填上 DEEPSEEK_API_KEY；本地向量与精排默认已开启
```

```bash
python -m askdata_pipeline.ecommerce_demo --query "客单价最高的10个用户是谁"
python -m askdata_pipeline.multi_turn_demo      # 五轮追问
python -m askdata_web.server                    # http://127.0.0.1:8000
```

模型分工：关键词抽取、CoT 规划、SQL 生成走 DeepSeek；向量和精排走本地
`bge-small-zh-v1.5` / `bge-reranker-base`（首次运行自动下载，约 1.2GB）。也支持阿里云百炼，
配置项见 [.env.example](.env.example) 和 [llm_config.py](llm_config.py)。不配任何 Key
时全部走 Mock，能跑通，但结果没有意义，降级记录里会写明。

## 数据集

- **ecommerce**：自建，11 表 81 字段，约 7000 行，固定随机种子。刻意埋了近义字段：9 个
  金额字段、两张表里都有的 `pay_amount` / `city` / `finish_time`、"客单价""销售额"这类
  和字段名字面零重合的业务词
- **Chinook**：公开的音乐商店库，11 表 64 字段，英文命名、中文提问。`Name` 出现在 5 张表，
  客户和员工共享 11 个同名字段——这些歧义不是我埋的

```bash
curl -L -o runtime_data/chinook.db \
  https://github.com/lerocha/chinook-database/raw/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite
```

**换成自己的库**：照着 [ecommerce_data.py](askdata_pipeline/ecommerce_data.py) 写建表语句
（外键一定要声明，表关系靠它提取）、业务元数据（别名和近义字段辨析最值钱）、在
`_prepare_dataset()` 里加一个分支。检索参数默认按大库设置，新库不用调；字段多到全量 Schema
超过 4 万字时，复核自动改用有限扩展（`REVIEW_SCHEMA_BOUNDED` 会写明用了哪一级）。

## 评测

```bash
python -m eval.runner --repeat 3                                # ecommerce 主题库
python -m eval.runner --dataset chinook --repeat 3
python -m eval.runner --case E36                                # 单题
python -m eval.runner --dataset chinook --meta ab --repeat 3    # 元数据消融
python -m eval.runner --bank holdout3 --repeat 3                # 留出集（已用过会提醒）
python -m eval.runner --repeat 3 --save-runs runtime_data/runs/main.jsonl   # 保存过程记录
```

- **比执行结果，不比 SQL 字符串**：行内值排序、行间集合比对，容忍列别名和列顺序。
  数值比到题面要求的小数位（"保留 N 位小数"，没写就是 2 位），取整规则和 SQLite 的
  `ROUND` 一致
- **分指标统计**：首轮检索召回、Schema 召回（含兜底）、执行准确率、陷阱题诚实率、端到端，
  分开看才知道错在哪一环
- **`--repeat`**：关键词抽取不确定，单次运行有约 ±5% 波动，按多数判定
- **熔断**：断网、Key 失效、余额耗尽这类故障连续 3 次就中止，而且一个百分比都不输出——
  半截数据算出来的准确率比没有更危险
- **`--save-runs`**：每次运行追加一行 JSON，带提交号、判定、降级详情、CoT 原文、结果样本，
  以及 `sql_trace`——执行过的每一条 SQL，包括守卫重规划前的首轮 SQL、回调修正前报错的 SQL、
  自洽性投票落选的几次。逐行落盘，评测中途熔断也不丢
- 并行跑时每个进程用不同的 `--db-path`，否则几个进程同时重建同一个库会报 disk I/O error

## 降级告警

链路上每一处已知的降级点都有探针，出问题时在 stderr 留一行告警，并通过
`PipelineResult.diagnostics` 带出来。常看的几个：

| Code | 含义 |
|---|---|
| `MODEL_MOCK_FALLBACK` / `EMBEDDING_MOCK_FALLBACK` / `RERANK_MOCK_FALLBACK` | 没配 Key 或本地模型，对应环节走了 Mock |
| `SCHEMA_RECALL_CAPPED` | 精排名额相对候选数过小，可能截掉了需要的字段 |
| `SCHEMA_RECALL_MISS` | 首轮检索漏召回，已用全量 Schema 复核救回 |
| `FILTER_VALUE_DROPPED` | 问题提到的枚举取值没出现在 SQL 里，筛选条件疑似被丢 |
| `TIME_FIELD_RESCUED` | 问题有时间约束，检索结果里缺时间字段，已补回 |
| `JOIN_PATH_BRIDGED` | 关键词落在的表之间不连通，已沿外键补上桥接表和关联键 |
| `REVIEW_SCHEMA_BOUNDED` | 全量 Schema 超出长度预算，复核 / 守卫重规划改用有限扩展，或不复核 |
| `EMPTY_RESULT_SET` | SQL 成功但返回 0 行，多轮追问里常见于凭空推断的 ID |

完整列表见 [askdata_diagnostics.py](askdata_diagnostics.py)。

## 局限与待办

- **只在 SQLite、最多 81 个字段的库上测过。**拒答复核和筛选值守卫重规划会把全量 Schema
  摆出来（约 200 字一个字段）；超出 `review_schema_char_budget`（默认 4 万字）时改用有限扩展——
  选中表的全部字段，能放下时再加外键一跳，都放不下就不复核。库越大复核越不完整，这条退路
  还没在真实的大库上测过
- **三处改动在陌生题上还没有可帮的题**：时间字段只留保底、筛选值守卫跳过题目自带口径的取值、
  候选池按关键词保底。第四套里没有题落在它们针对的失败形态上，收益未测出，代价也未测出
- **判分的局限**：每行的值先排序再比，把员工和上级的名字对调也会判对

## 测试

```bash
python -m unittest discover -s tests
```

单元测试不读 `.env`、不调真实模型，几秒跑完。每次推送和 PR 由 GitHub Actions 自动跑一遍
（[tests.yml](.github/workflows/tests.yml)），装 `requirements.txt` 里除本地模型那组以外的依赖。
