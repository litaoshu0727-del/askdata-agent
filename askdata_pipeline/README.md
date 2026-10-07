# askdata_pipeline

端到端编排：把检索、规划、生成、执行串成一条链路，外面再套一层路由和多轮追问。

## 入口

| 类 | 用途 |
|---|---|
| `AskDataText2SQLPipeline` | 单轮 Text2SQL：问题 → SQL → 结果 + 降级记录 |
| `DynamicAskDataService` | 带记忆和路由：要查新数据走 Text2SQL，结果解释、指标口径、历史追问走 `data_qa`，不查库 |

```python
from askdata_memory import ConversationMemoryService
from askdata_pipeline import AskDataText2SQLPipeline, DynamicAskDataService
from askdata_pipeline.objects import PipelineConfig

pipeline = AskDataText2SQLPipeline(PipelineConfig(
    dataset="ecommerce",
    database_name="ecommerce_db",
    db_path="runtime_data/ecommerce_demo.db",   # 不写会落到默认的 trade_demo.db
))
service = DynamicAskDataService(pipeline, ConversationMemoryService())

response = service.run(user_id="u1", session_id="s1", query="销售额最高的三个店铺是哪些")
print(response.decision.route.value, response.answer)
```

## 文件

| 文件 | 内容 |
|---|---|
| `text2sql_pipeline.py` | 主链路编排；全量 Schema 复核、SQL 回调修正、自洽性投票、筛选值守卫都在这里接入 |
| `dynamic_service.py` `routing.py` `data_qa.py` | 统一入口、路由判定、不查库的问答 |
| `query_rewriter.py` | 指代消解：把"它们"改写成上一轮的具体对象 |
| `filter_guard.py` | 筛选值守卫：问题提到的枚举取值 SQL 没用上，就带提示重规划 |
| `conversation_service.py` | 多轮会话编排 |
| `ecommerce_data.py` `chinook_data.py` `demo_data.py` | 三个数据集的建库与业务元数据 |
| `local_clients.py` | 无 Key 时的 Mock 关键词抽取与向量 |
| `objects.py` | `PipelineConfig`、`PipelineResult` 等数据结构 |

## Demo

```bash
python -m askdata_pipeline.ecommerce_demo --query "客单价最高的10个用户是谁"
python -m askdata_pipeline.multi_turn_demo          # 五轮追问：指代消解、复用历史结果、指标口径
python -m askdata_pipeline.memory_end_to_end_demo   # 长短期记忆 + 路由
python -m askdata_pipeline.end_to_end_demo          # 原作者的 trade 库 Demo
python -m askdata_pipeline.sql_execution_demo       # 只测执行环境，不调模型
```

## 几条要知道的事

- **指代消解是独立的一步**，放在关键词抽取之前；只有检测到"它们、这些、刚才"这类指代词才调
  模型。改写提示词里明确禁止凭空推断 ID，见[指代消解](../docs/实验记录.md#指代消解是独立的一步)
- **筛选值守卫不查题目自带口径的取值**，比如"已支付过的订单（支付时间不为空）"，见
  [题目自带口径的取值](../docs/实验记录.md#题目自带口径的取值守卫不再查)
- **SQL 回调修正默认开启，自洽性投票默认关闭**：投票在当前模型上净效果为零、成本 2.7 倍，见
  [结果校验与回调修正](../docs/实验记录.md#结果校验与回调修正--自洽性投票)
- **接自己的库**：在 `text2sql_pipeline.py` 的 `_prepare_dataset()` 里加一个分支，照着
  `ecommerce_data.py` 写建表语句和业务元数据
