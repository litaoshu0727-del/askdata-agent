# askdata_memory

长短期记忆。不依赖 Web 框架，由 `DynamicAskDataService` 调用，也可以单独用。

| 文件 | 内容 |
|---|---|
| `conversation.py` | `ConversationMemoryService`：统一入口 |
| `short_term.py` | 短期记忆：滑动窗口 + 异步增量摘要 |
| `long_term.py` | 长期记忆：个人知识库的保存与召回 |
| `summarizer.py` | 模型摘要与离线抽取式摘要 |
| `storage.py` | SQLite 持久化 |
| `vector_store.py` | Milvus 向量索引（可选） |
| `reranker.py` | 长期记忆召回的精排（可选） |
| `objects.py` | 数据结构与配置 |

## 短期记忆

- 完整原始消息存 SQLite；按最近消息数和估算 Token 数维护滑动窗口
- 窗口外的消息由后台线程增量压缩成摘要，不阻塞当前请求；摘要带版本和游标，不重复、不遗漏
- 摘要保留用户目标、业务口径、筛选条件、SQL 结果、分析结论和任务状态
- 配了大模型（DeepSeek 或阿里云百炼）就用模型写摘要，没配就用离线抽取式摘要

## 长期记忆

- **只有显式调用保存方法才写入**，对应用户的"保存到个人知识库"动作
- 存"检索摘要 + 原始内容 + 元信息 + 向量"；结构化结果的元信息包括库、表、字段、筛选条件、
  CoT 和 SQL
- 召回严格按 `user_id` 隔离，只有 `enable_long_term=True` 时才检索
- 默认用 SQLite 存向量；设置 `MemoryServiceConfig(milvus_uri=...)` 后改用 Milvus Lite 或
  Milvus 服务
- 精排可选：配了阿里云百炼 Rerank 就用它，否则在 `ASKDATA_LOCAL_MODELS=1` 时用本地
  bge-reranker，都没有就按向量相似度排序

## 用法

```python
from askdata_memory import ConversationMemoryService

memory = ConversationMemoryService()

context = memory.begin_user_turn(
    user_id="user-1", session_id="session-1",
    query="上次的交易利率是多少？", enable_long_term=True,
)
# context.to_prompt_context() 交给对话模型或查询链路

memory.record_assistant_message(
    user_id="user-1", session_id="session-1",
    content="查询结果为 3.5%", message_type="sql_result",
    payload={"interest_rate": 0.035},
)

# 用户点了"保存"才调用
memory.save_structured_result(
    user_id="user-1", query="查询交易利率",
    result={"interest_rate": 0.035},
    database="trade_db", tables=["interest_info"], columns=["interest_rate"],
    sql="SELECT interest_rate FROM interest_info ...",
)
```

接进 Text2SQL 链路的写法见 [askdata_pipeline](../askdata_pipeline/README.md)。

## Demo 与测试

```bash
python -m askdata_pipeline.memory_end_to_end_demo
python -m unittest tests.test_memory tests.test_routing
```

Demo 依次展示：第一轮查库、短期窗口、主动保存长期记忆、第二轮长期召回（路由到 `data_qa`，
不重复查库）、异步摘要完成后的上下文。记忆默认存在 `runtime_data/memory_demo.db`。
