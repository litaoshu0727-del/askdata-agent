# cot_planning

CoT 规划：拿检索出的局部 Schema，把问题拆成一步或几步四元组（数据库、处理对象、操作指令、
输出目标），交给 SQL 生成。

| 文件 | 内容 |
|---|---|
| `cot_planner.py` | 规划主流程，`plan` / `plan_stream` |
| `prompt_builder.py` | 规划提示词 |
| `thinking_client.py` | 思考模型调用，支持流式输出 |
| `objects.py` | 数据结构 |
| `cot_planning_demo.py` | 流式输出 Demo |

```bash
python -m cot_planning.cot_planning_demo
```

模型由 [llm_config.py](../llm_config.py) 统一解析：DeepSeek 优先，开启 thinking 模式；
其次阿里云百炼；都没配置时走 Mock。

规划判"缺失"时，主链路会先用全量 Schema 复核一次再决定拒答，见
[拒答必须建立在完整信息上](../docs/实验记录.md#拒答必须建立在完整信息上)。四元组的解析在
[sql_generation/cot_parser.py](../sql_generation/cot_parser.py)。
