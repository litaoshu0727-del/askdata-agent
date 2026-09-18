"""
电商数据集端到端 Demo。

执行：
    python -m askdata_pipeline.ecommerce_demo
    python -m askdata_pipeline.ecommerce_demo --query "客单价最高的10个用户是谁"

这套数据集有 11 张表 81 个字段，近义字段密集，
用它才能看出两阶段检索到底有没有把对的字段捞上来。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402

# 每条 Query 后面标注的是"应该命中哪些字段"，方便你对照检索结果判断准确率。
DEFAULT_QUERIES = [
    (
        "销售额最高的三个店铺是哪些",
        "考点：业务口头说的“销售额”对应的字段名是 gmv，"
        "而库里还有 order_amount / pay_amount / item_amount 等 8 个金额字段在干扰。",
    ),
    (
        "累计消费金额超过30000的用户来自哪些城市",
        "考点：“累计消费金额”对应 dws_user_summary.total_pay_amount，"
        "“城市”对应 dim_user.city，而 dim_shop 里也有一个 city 字段是店铺所在地。",
    ),
    (
        "客单价最高的10个用户是谁",
        "考点：“客单价”是纯业务口头表达，字段名叫 avg_order_amount，"
        "字面上没有任何一个字能对上，只能靠别名和语义召回。",
    ),
    (
        "因为商品质量问题退款的总金额是多少",
        "考点：需要同时命中 refund_reason 和 refund_amount，"
        "且要避免被 order_amount、pay_amount 等金额字段带偏。",
    ),
]


def print_section(title: str) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def run_query(pipeline: AskDataText2SQLPipeline, query: str, note: str = "") -> None:
    """跑一条 Query 并打印关键环节。"""
    print_section(f"Query：{query}")

    if note:
        print(note + "\n")

    result = pipeline.run(query)

    print("【1】抽取的检索关键词")
    print("    " + "，".join(result.keywords))

    hit_columns = []
    for line in result.schema_context.splitlines():
        stripped = line.strip()
        if stripped.startswith("表名："):
            hit_columns.append(f"\n    {stripped}")
        elif stripped.startswith("- 字段名："):
            hit_columns.append("      " + stripped.replace("- 字段名：", ""))

    print("\n【2】Schema 检索命中的表与字段")
    print("\n".join(hit_columns))

    print("\n【3】CoT 四元组")
    for line in result.cot_output.strip().splitlines():
        print("    " + line)

    for index, log in enumerate(result.step_logs, start=1):
        print(f"\n【4.{index}】生成的 SQL")
        for line in log.sql.strip().splitlines():
            print("    " + line)

        print(f"\n【5.{index}】执行结果")
        execution = log.execution_result

        if not execution.get("success"):
            print("    ❌ 执行失败：" + str(execution.get("error")))
            continue

        rows = execution.get("rows") or []
        print(f"    返回 {execution.get('row_count')} 行")

        for row in rows[:10]:
            print("    " + json.dumps(row, ensure_ascii=False))

        if len(rows) > 10:
            print(f"    ……（仅展示前 10 行，共 {len(rows)} 行）")

    print("\n【6】降级记录")

    if not result.diagnostics:
        print("    无降级，链路每一环都在满配置下跑完")
    else:
        for item in result.diagnostics:
            print("    ⚠️  " + item.render())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AskData 电商数据集 Demo")
    parser.add_argument("--query", default="", help="自定义 Query；不传则跑内置的 4 条")
    parser.add_argument(
        "--db-path",
        default=str(Path("runtime_data") / "ecommerce_demo.db"),
        help="电商 Demo 数据库路径",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    # 降级记录跟在每条 Query 后面展示，这里关掉 logging 避免和正文输出交错。
    logging.getLogger("askdata").disabled = True

    pipeline = AskDataText2SQLPipeline(
        PipelineConfig(
            dataset="ecommerce",
            database_name="ecommerce_db",
            db_path=Path(args.db_path),
            sample_size=5,
        )
    )

    if args.query:
        run_query(pipeline, args.query)
        return

    for query, note in DEFAULT_QUERIES:
        run_query(pipeline, query, note)


if __name__ == "__main__":
    main()
