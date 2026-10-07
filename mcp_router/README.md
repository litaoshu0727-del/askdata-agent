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

只测执行环境、不调模型：

```bash
python -m askdata_pipeline.sql_execution_demo
```
