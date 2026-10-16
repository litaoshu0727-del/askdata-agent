# mcp_router

按库名把 SQL 路由到对应的执行器。目前只有 SQLite 执行器。

| 文件 | 内容 |
|---|---|
| `router.py` | `MCPRouter`：注册执行器、按 `database` 分发 |
| `sqlite_executor.py` | `SQLiteMCPExecutor`；`unique_column_names` 给同名列去重 |
| `objects.py` | 执行请求与执行结果 |

执行请求格式：

```json
{"database": "trade_db", "sql": "SELECT ..."}
```

**同名列不会被合并。**自关联这类查询会返回同名列（两列 `FirstName`），原先转字典时后一列
覆盖前一列，用户只看到半张表。现在重名的列依次加 `_2`、`_3`，按位置填值；评测器算参考答案
用的是同一个函数。见[同名列被合并](../docs/实验记录.md#同名列被合并执行层和裁判的同一个坑)。

**执行限制**（SQL 是模型写的）：

- **只读**：用 `mode=ro` 打开库，再加 `PRAGMA query_only`。只看 SQL 开头挡不住
  `WITH … DELETE`
- **时长**：单条查询最多 30 秒（`max_seconds`），漏了关联条件的笛卡尔积会被中断
- **行数**：最多取回 1 万行（`max_rows`，链路里是 `PipelineConfig.max_result_rows`），超出的截掉，
  结果带 `truncated`，链路告警 `RESULT_TRUNCATED`。时长管不住快速返回的大结果：漏了 `GROUP BY`
  的明细查询几百毫秒就能吐出几十万行，原先全部取回，再整份存进会话记忆。1 万行比几个评测库里
  最大的表（8715 行）还大，真被截断多半是 SQL 写错了

只测执行环境、不调模型：

```bash
python -m askdata_pipeline.sql_execution_demo
```
