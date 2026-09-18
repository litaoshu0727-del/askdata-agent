"""
评测器。

三个指标分开统计，因为它们定位到不同的环节：

    Schema 召回率   该命中的字段有没有被检索召回  → 检索环节
    执行准确率      结果集与参考答案是否一致      → 生成环节
    端到端准确率    整条链路                      → 总分

召回 92% 但端到端 61%，说明问题在 CoT 或 SQL 生成；两个都低，说明元数据没写好。
一个总分只能告诉你"不行"，三个分指标才能告诉你"哪不行"。

执行：
    python -m eval.runner
    python -m eval.runner --case E03          # 只跑一道
    python -m eval.runner --tag 纯口径词       # 只跑某类
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402
from eval.cases import CASES, EvalCase  # noqa: E402
from eval.cases_extra import EXTRA_CASES  # noqa: E402

ALL_CASES: List[EvalCase] = CASES + EXTRA_CASES

# Schema 支撑不了时，CoT 里应该出现的措辞
MISSING_MARKERS = ("缺失", "无法", "不存在", "未找到", "没有", "不支持", "不足")

FLOAT_NDIGITS = 2


@dataclass
class CaseOutcome:
    """单题结果。"""

    case: EvalCase
    status: str                       # pass / wrong_result / sql_error / no_sql / crash
    hit_columns: Set[str] = field(default_factory=set)
    missed_columns: List[str] = field(default_factory=list)
    generated_sql: str = ""
    detail: str = ""
    elapsed: float = 0.0
    diagnostics: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    attempts: int = 1
    """实际尝试次数。超时等瞬时故障会重试。"""

    @property
    def schema_recall(self) -> float:
        total = len(self.case.must_hit_columns)
        if not total:
            return 1.0
        return len(self.hit_columns) / total


def normalize_value(value: Any) -> str:
    """把单元格归一化成可比较的字符串。"""
    if value is None:
        return "∅"

    if isinstance(value, bool):
        return str(value)

    if isinstance(value, (int, float)):
        return f"{round(float(value), FLOAT_NDIGITS):.{FLOAT_NDIGITS}f}"

    text = str(value).strip()

    # 数字型字符串也按数值归一，避免 "53" 和 "53.0" 判不一致
    try:
        return f"{round(float(text), FLOAT_NDIGITS):.{FLOAT_NDIGITS}f}"
    except ValueError:
        return text


def normalize_rows(rows: Sequence[Dict[str, Any]], ordered: bool) -> List[Tuple[str, ...]]:
    """
    把结果集归一化成可比较的形式。

    只比**值**，不比列名——同一个问题，列别名可以叫 gmv、total_gmv、
    SUM(d.gmv)，都是对的。行内值排序则是为了容忍列顺序不同。
    """
    normalized = [tuple(sorted(normalize_value(v) for v in row.values())) for row in rows]
    return normalized if ordered else sorted(normalized)


def parse_hit_columns(schema_context: str) -> Set[str]:
    """从 SchemaGraph 文本里解析出被召回的 表.字段 集合。"""
    hits: Set[str] = set()
    current_table = ""

    for line in schema_context.splitlines():
        stripped = line.strip()

        table_match = re.match(r"^表名[：:]\s*(\S+)", stripped)
        if table_match:
            current_table = table_match.group(1)
            continue

        column_match = re.match(r"^-\s*字段名[：:]\s*(\S+)", stripped)
        if column_match and current_table:
            hits.add(f"{current_table}.{column_match.group(1)}")

    return hits


def score_requirements(
    requirements: Sequence[Any],
    hit_columns: Set[str],
) -> Tuple[Set[str], List[str]]:
    """
    统计必中字段的命中情况。

    每条 requirement 可以是一个字段名，也可以是一组候选（命中任意一个即可）。
    """
    matched: Set[str] = set()
    missed: List[str] = []

    for requirement in requirements:
        options = [requirement] if isinstance(requirement, str) else list(requirement)
        hit = next((option for option in options if option in hit_columns), None)

        if hit:
            matched.add(hit)
        else:
            missed.append(" 或 ".join(options))

    return matched, missed


def load_expected(db_path: Path, case: EvalCase) -> List[Dict[str, Any]]:
    """执行参考 SQL，得到标准答案。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(case.reference_sql).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def run_case_with_retry(
    pipeline: AskDataText2SQLPipeline,
    db_path: Path,
    case: EvalCase,
    retries: int,
) -> CaseOutcome:
    """
    跑一道题，瞬时故障自动重试。

    超时、连接中断这类基础设施故障不该被记成"模型答错"——
    否则评测数字里混进了网络抖动，跨次对比就失去意义。
    """
    for attempt in range(1, retries + 2):
        outcome = run_case(pipeline, db_path, case)
        outcome.attempts = attempt

        if outcome.status != "crash" or attempt > retries:
            return outcome

        print(f"{'':<8}↻ 瞬时故障，重试 {attempt}/{retries}：{outcome.detail[:60]}", flush=True)

    return outcome


def run_case(pipeline: AskDataText2SQLPipeline, db_path: Path, case: EvalCase) -> CaseOutcome:
    """跑一道题。"""
    expected = load_expected(db_path, case)
    started = time.time()

    try:
        result = pipeline.run(case.query)
    except Exception as exc:
        return CaseOutcome(
            case=case,
            status="crash",
            detail=f"{type(exc).__name__}: {exc}",
            elapsed=time.time() - started,
        )

    elapsed = time.time() - started
    hit_columns = parse_hit_columns(result.schema_context)
    matched, missed = score_requirements(case.must_hit_columns, hit_columns)
    diagnostics = [item.code for item in result.diagnostics]

    base = dict(
        case=case,
        hit_columns=matched,
        missed_columns=missed,
        elapsed=elapsed,
        diagnostics=diagnostics,
    )

    if case.expect_unanswerable:
        return judge_unanswerable(result, base)

    if not result.step_logs:
        return CaseOutcome(status="no_sql", detail="CoT 未解析出步骤，未生成 SQL", **base)

    last = result.step_logs[-1]
    generated_sql = " ".join(last.sql.split())
    execution = last.execution_result

    if not execution.get("success"):
        return CaseOutcome(
            status="sql_error",
            generated_sql=generated_sql,
            detail=str(execution.get("error"))[:120],
            **base,
        )

    actual = execution.get("rows") or []

    if normalize_rows(actual, case.ordered) == normalize_rows(expected, case.ordered):
        return CaseOutcome(status="pass", generated_sql=generated_sql, **base)

    return CaseOutcome(
        status="wrong_result",
        generated_sql=generated_sql,
        detail=f"期望 {len(expected)} 行，实际 {len(actual)} 行",
        **base,
    )


def judge_unanswerable(result: Any, base: Dict[str, Any]) -> CaseOutcome:
    """
    判陷阱题。

    只看一件事：有没有编。明确说缺失、或干脆没生成 SQL，都算通过；
    一本正经地返回一个结果集，算失败。
    """
    flagged = any(marker in result.cot_output for marker in MISSING_MARKERS)

    if not result.step_logs:
        return CaseOutcome(status="pass", detail="未生成 SQL，正确", **base)

    last = result.step_logs[-1]
    generated_sql = " ".join(last.sql.split())
    execution = last.execution_result

    if flagged and not execution.get("rows"):
        return CaseOutcome(
            status="pass",
            generated_sql=generated_sql,
            detail="CoT 已说明缺失，未给出结果",
            **base,
        )

    if not execution.get("success"):
        return CaseOutcome(
            status="pass",
            generated_sql=generated_sql,
            detail=f"未编造，SQL 执行失败：{str(execution.get('error'))[:60]}",
            **base,
        )

    if flagged:
        return CaseOutcome(
            status="pass",
            generated_sql=generated_sql,
            detail="CoT 已说明缺失",
            **base,
        )

    return CaseOutcome(
        status="fabricated",
        generated_sql=generated_sql,
        detail=f"Schema 支撑不了，却返回了 {execution.get('row_count')} 行结果",
        **base,
    )


STATUS_LABEL = {
    "pass": "✅ 通过",
    "fabricated": "❌ 编造了答案",
    "wrong_result": "❌ 结果不符",
    "sql_error": "❌ SQL 报错",
    "no_sql": "❌ 未生成 SQL",
    "crash": "❌ 链路异常",
}


def report(outcomes: List[CaseOutcome]) -> None:
    """打印评测报告。"""
    total = len(outcomes)
    passed = sum(1 for item in outcomes if item.passed)

    must_hit_total = sum(len(item.case.must_hit_columns) for item in outcomes)
    must_hit_matched = sum(len(item.hit_columns) for item in outcomes)
    must_hit_total = must_hit_total or 1

    normal = [item for item in outcomes if not item.case.expect_unanswerable]
    traps = [item for item in outcomes if item.case.expect_unanswerable]
    executed = [item for item in normal if item.status in {"pass", "wrong_result"}]

    print("\n" + "=" * 92)
    print("逐题结果")
    print("=" * 92)
    print(f"{'ID':<6}{'结果':<14}{'召回':<9}{'耗时':<9}问题")

    for item in outcomes:
        recall = f"{len(item.hit_columns)}/{len(item.case.must_hit_columns)}"
        print(
            f"{item.case.id:<6}{STATUS_LABEL[item.status]:<15}"
            f"{recall:<10}{item.elapsed:>5.1f}s   {item.case.query}"
        )
        if not item.passed:
            print(f"{'':<6}└─ {item.detail}")
            if item.missed_columns:
                print(f"{'':<6}   漏召回：{'、'.join(item.missed_columns)}")
            if item.generated_sql:
                print(f"{'':<6}   生成的 SQL：{item.generated_sql[:150]}")

    print("\n" + "=" * 92)
    print("指标")
    print("=" * 92)
    print(f"  Schema 召回率    {must_hit_matched}/{must_hit_total}"
          f"　{must_hit_matched / must_hit_total:.0%}　"
          f"（该命中的字段有没有被召回 → 检索环节）")

    if executed:
        exec_pass = sum(1 for item in executed if item.passed)
        print(f"  执行准确率       {exec_pass}/{len(executed)}"
              f"　{exec_pass / len(executed):.0%}　"
              f"（跑得出结果的题里，结果对不对 → 生成环节）")
    else:
        print("  执行准确率       —")

    if traps:
        honest = sum(1 for item in traps if item.passed)
        print(f"  陷阱题诚实率     {honest}/{len(traps)}"
              f"　{honest / len(traps):.0%}　"
              f"（Schema 支撑不了时，会不会编一个答案）")

    print(f"  端到端准确率     {passed}/{total}"
          f"　{passed / total:.0%}　"
          f"（整条链路，含陷阱题）")

    failures: Dict[str, int] = {}
    for item in outcomes:
        if not item.passed:
            failures[item.status] = failures.get(item.status, 0) + 1

    if failures:
        print("\n  失败构成：" + "，".join(
            f"{STATUS_LABEL[status].replace('❌ ', '')} {count} 题"
            for status, count in sorted(failures.items())
        ))

    tag_stats: Dict[str, List[int]] = {}
    for item in outcomes:
        for tag in item.case.tags:
            bucket = tag_stats.setdefault(tag, [0, 0])
            bucket[1] += 1
            if item.passed:
                bucket[0] += 1

    print("\n" + "=" * 92)
    print("按考点拆分")
    print("=" * 92)
    for tag, (ok, count) in sorted(tag_stats.items(), key=lambda kv: (kv[1][0] / kv[1][1], -kv[1][1])):
        bar = "█" * ok + "░" * (count - ok)
        print(f"  {tag:<14}{ok}/{count}  {bar}")

    all_diagnostics: Dict[str, int] = {}
    for item in outcomes:
        for code in item.diagnostics:
            all_diagnostics[code] = all_diagnostics.get(code, 0) + 1

    if all_diagnostics:
        print("\n" + "=" * 92)
        print("降级记录")
        print("=" * 92)
        for code, count in sorted(all_diagnostics.items(), key=lambda kv: -kv[1]):
            print(f"  {code:<26}{count} 题次")

    print(f"\n总耗时 {sum(item.elapsed for item in outcomes):.1f}s，"
          f"平均每题 {sum(item.elapsed for item in outcomes) / total:.1f}s")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AskData 电商数据集评测")
    parser.add_argument("--case", default="", help="只跑指定题号，例如 E03")
    parser.add_argument("--tag", default="", help="只跑指定考点")
    parser.add_argument("--retries", type=int, default=2, help="瞬时故障重试次数")
    parser.add_argument(
        "--db-path",
        default=str(Path("runtime_data") / "eval_ecommerce.db"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.getLogger("askdata").disabled = True

    cases: List[EvalCase] = list(ALL_CASES)
    if args.case:
        cases = [item for item in cases if item.id.upper() == args.case.upper()]
    if args.tag:
        cases = [item for item in cases if args.tag in item.tags]

    if not cases:
        print("没有匹配的题目")
        return

    db_path = Path(args.db_path)

    print("=" * 92)
    print(f"AskData 评测　·　电商数据集　·　{len(cases)} 题")
    print("=" * 92)

    pipeline = AskDataText2SQLPipeline(
        PipelineConfig(
            dataset="ecommerce",
            database_name="ecommerce_db",
            db_path=db_path,
            sample_size=5,
        )
    )

    outcomes = []
    for index, case in enumerate(cases, start=1):
        print(f"  [{index}/{len(cases)}] {case.id} {case.query}", flush=True)
        outcomes.append(run_case_with_retry(pipeline, db_path, case, args.retries))

    report(outcomes)


if __name__ == "__main__":
    main()
