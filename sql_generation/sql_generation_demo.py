from __future__ import annotations

import json

from .coder_client import CoderModelClient, CoderModelConfig
from .cot_parser import CotStepParser
from .schema_store import LocalSchemaStore
from .sql_generator import SqlGenerator


def build_demo_cot_text() -> str:
    """
    构造 Demo CoT 四元组。

    这里模拟上一阶段 CoT Planning 的输出。
    """
    return """步骤1：
(
数据库: trade_db,
处理对象: trade_summary.total_trade_count，interest_info.interest_rate，trade_summary.user_id，interest_info.user_id，trade_summary.user_id ↔ interest_info.user_id,
操作指令: 先在trade_summary表中筛选total_trade_count大于50000的记录，并获取对应user_id；再基于user_id关联interest_info表；最后获取对应的interest_rate,
输出目标: interest_info.interest_rate
)"""


def main() -> None:
    """
    运行 Demo。

    供应商、Key 和模型名由 llm_config 统一解析（DeepSeek 优先，其次阿里云百炼），
    和主链路一致；都没配置时走 Mock。

    原先这里写死了 DASHSCOPE_API_KEY 和 DASHSCOPE_CODER_MODEL（默认 qwen-plus）。只配
    DeepSeek 时，客户端从 llm_config 拿到了 DeepSeek 的 Key，模型名却还是
    qwen-plus，请求直接 HTTP 400。
    """
    cot_text = build_demo_cot_text()

    parser = CotStepParser()
    cot_step = parser.parse_one(cot_text)

    schema_store = LocalSchemaStore.build_demo_store()

    generator = SqlGenerator(
        schema_store=schema_store,
        coder_client=CoderModelClient(
            CoderModelConfig(
                temperature=0.0,
                use_mock_when_no_api_key=True,
            )
        )
    )

    result = generator.generate(cot_step)

    print("=" * 80)
    print("Coder Prompt")
    print("=" * 80)
    print(result.prompt)

    print("\n" + "=" * 80)
    print("SQL")
    print("=" * 80)
    print(result.sql)

    print("\n" + "=" * 80)
    print("Execution Request")
    print("=" * 80)
    print(
        json.dumps(
            result.to_execution_request(),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
