# sql_generation

SQL 生成：解析 CoT 四元组，取出这一步用到的局部 Schema（含样例值），生成 SQL；执行报错时
把报错喂回去生成修正版。

| 文件 | 内容 |
|---|---|
| `sql_generator.py` | 生成主流程 |
| `prompt_builder.py` | 生成提示词 `build` 和修正提示词 `build_repair`，SQLite 规则写在这里 |
| `cot_parser.py` | 正则解析 CoT 四元组，兼容多种标点写法 |
| `schema_store.py` | 局部 Schema 存储与提取 |
| `coder_client.py` | 模型调用；顺带剥掉 SQL 里多余的库名前缀 |
| `objects.py` | 数据结构 |
| `sql_generation_demo.py` | Demo |

```bash
python -m sql_generation.sql_generation_demo
```

模型由 [llm_config.py](../llm_config.py) 统一解析：DeepSeek 优先，关闭 thinking 让
`temperature=0` 生效；其次阿里云百炼；都没配置时走 Mock。

**提示词里的 SQLite 规则**是从具体失败里来的，每条的出处写在 `SqlPromptBuilder` 的文档字符串里：
日期区间不要写成字符串 `BETWEEN`、日期字面量用 `YYYY-MM-DD`、整数相除先乘 1.0、跨表比例
各自用子查询。生成和修正两份提示词都要有，改的时候两处一起改，
[tests/test_sql_prompt.py](../tests/test_sql_prompt.py) 会检查。见
[SQL 生成看不到样例值](../docs/实验记录.md#sql-生成看不到样例值)、
[整数相除，和跨表比例](../docs/实验记录.md#整数相除和跨表比例)。

执行请求格式（交给 [mcp_router](../mcp_router/README.md)）：

```json
{"database": "trade_db", "sql": "SELECT ..."}
```
