from __future__ import annotations

import json
import logging
from pathlib import Path

from .objects import PipelineConfig
from .text2sql_pipeline import AskDataText2SQLPipeline


def main() -> None:
    """
    端到端 Demo。

    执行：
        python -m askdata_pipeline.end_to_end_demo
    """
    # 降级记录统一在最后集中展示，这里关掉 logging 避免和正文输出交错。
    logging.getLogger("askdata").disabled = True

    query = "查询总交易笔数大于50000的利率是多少"

    pipeline = AskDataText2SQLPipeline(
        PipelineConfig(
            database_name="trade_db",
            db_path=Path("runtime_data") / "trade_demo.db",
            sample_size=5,
        )
    )

    result = pipeline.run(query)

    print("=" * 80)
    print("1. 用户 Query")
    print("=" * 80)
    print(result.query)

    print("\n" + "=" * 80)
    print("2. Schema 检索关键词")
    print("=" * 80)
    print("，".join(result.keywords))

    print("\n" + "=" * 80)
    print("3. Schema 图")
    print("=" * 80)
    print(result.schema_context)

    print("\n" + "=" * 80)
    print("4. CoT 四元组")
    print("=" * 80)
    print(result.cot_output)

    for index, log in enumerate(result.step_logs, start=1):
        print("\n" + "=" * 80)
        print(f"5.{index} 当前步骤局部 Schema")
        print("=" * 80)
        print(log.local_schema)

        print("\n" + "=" * 80)
        print(f"6.{index} SQL")
        print("=" * 80)
        print(log.sql)

        print("\n" + "=" * 80)
        print(f"7.{index} MCP 执行请求")
        print("=" * 80)
        print(
            json.dumps(
                log.execution_request,
                ensure_ascii=False,
                indent=2,
            )
        )

        print("\n" + "=" * 80)
        print(f"8.{index} MCP 执行结果")
        print("=" * 80)
        print(
            json.dumps(
                log.execution_result,
                ensure_ascii=False,
                indent=2,
            )
        )

    print("\n" + "=" * 80)
    print("9. 本次运行的降级记录")
    print("=" * 80)

    if not result.diagnostics:
        print("无降级，链路每一环都在满配置下跑完。")
    else:
        print(f"共 {len(result.diagnostics)} 条。结果看着正常，但以下环节实际已经打了折扣：\n")
        for item in result.diagnostics:
            print("  ⚠️  " + item.render())


if __name__ == "__main__":
    main()
