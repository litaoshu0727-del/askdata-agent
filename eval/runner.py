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
    python -m eval.runner --dataset chinook --meta ab --repeat 3
                                              # 元数据消融：有/无两组逐题交错跑，输出差值
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402
from eval.cases import CASES, EvalCase  # noqa: E402
from eval.cases_chinook import CHINOOK_CASES  # noqa: E402
from eval.cases_extra import EXTRA_CASES  # noqa: E402

ALL_CASES: List[EvalCase] = CASES + EXTRA_CASES

# 数据集 → (题库, 数据库名, 默认库路径)
DATASETS = {
    "ecommerce": (ALL_CASES, "ecommerce_db", Path("runtime_data") / "eval_ecommerce.db"),
    "chinook": (CHINOOK_CASES, "chinook_db", Path("runtime_data") / "chinook.db"),
}

# 留出集：由没见过系统失败情况的出题人编写。
#
# 主题库调到满分之后就测不出东西了——那些改动是被具体失败题一道道驱动出来的，
# 题库本身也改过问法。一把满分的秤既测不出下一个改进，也测不出过拟合。
# 这套题写完先冻结再跑，之后只允许修"可证明没法判分"的题，并且逐条记录。
#
# 只兜 ImportError：文件存在但写坏了（语法错误）应该直接炸出来，不能悄悄变成空题库。
try:
    from eval.cases_holdout import (  # noqa: E402
        HOLDOUT_CHINOOK_CASES,
        HOLDOUT_ECOMMERCE_CASES,
    )
except ImportError:
    HOLDOUT_ECOMMERCE_CASES, HOLDOUT_CHINOOK_CASES = [], []

HOLDOUT_BANKS = {
    "ecommerce": HOLDOUT_ECOMMERCE_CASES,
    "chinook": HOLDOUT_CHINOOK_CASES,
}

# 第二套留出集：只有 Chinook。
#
# 第一套被拿来诊断过（Chinook 员工题的精排问题就是从它的失败里查出来的），
# 已经不能再用来验证那次修改。这一套由另一个盲写出题人编写，
# 对修改前、修改后两个版本都是没见过的题——两者的差值才是修改在陌生问题上的效果。
try:
    from eval.cases_holdout2 import HOLDOUT2_CHINOOK_CASES  # noqa: E402
except ImportError:
    HOLDOUT2_CHINOOK_CASES = []

HOLDOUT2_BANKS = {
    "ecommerce": [],
    "chinook": HOLDOUT2_CHINOOK_CASES,
}

BANKS = {
    "holdout": HOLDOUT_BANKS,
    "holdout2": HOLDOUT2_BANKS,
}

# Schema 支撑不了时，CoT 里应该出现的措辞
MISSING_MARKERS = ("缺失", "无法", "不存在", "未找到", "没有", "不支持", "不足")

FLOAT_NDIGITS = 2

# 持续性故障：重试毫无意义，环境本身不通
PERSISTENT_ERROR_PATTERNS = (
    "nodename nor servname",               # macOS DNS 解析失败
    "name or service not known",           # Linux DNS 解析失败
    "temporary failure in name resolution",
    "connection refused",
    "no route to host",
    "network is unreachable",
    "certificate verify failed",
    "unauthorized",                        # Key 失效
    "insufficient balance",                # 余额耗尽
    "401",
    "402",
    "403",
)

# 瞬时故障：重试有意义
TRANSIENT_ERROR_PATTERNS = (
    "timed out",
    "timeout",
    "too many requests",
    "connection reset",
    "remotedisconnected",
    "bad gateway",
    "429",
    "502",
    "503",
    "504",
)


class EvalAborted(RuntimeError):
    """
    连续多题因同一类基础设施故障失败，评测中止。

    动机：一次 150 运行的评测跑到一半断网，后面 26 题全部 0.0 秒失败，
    重试机制空转 162 次，最后仍然吐出一份格式完整的报告——端到端 42%、
    陷阱题诚实率 0/5、"三次运行波动 0 题"。

    每个数字都是假的，但报告看起来毫无异常。如果不逐题看耗时，
    很可能把它当成真实退步，然后去修一个根本不存在的问题。

    一个会输出无效数字的评测器，比没有评测器更危险。
    """

    def __init__(self, reason: str, completed: int, total: int, consecutive: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.completed = completed
        self.total = total
        self.consecutive = consecutive


def classify_error(detail: str) -> str:
    """把报错归类成 persistent / transient / unknown。"""
    text = (detail or "").lower()

    for pattern in PERSISTENT_ERROR_PATTERNS:
        if pattern in text:
            return "persistent"

    for pattern in TRANSIENT_ERROR_PATTERNS:
        if pattern in text:
            return "transient"

    return "unknown"


@dataclass
class CaseOutcome:
    """单题结果。"""

    case: EvalCase
    status: str                       # pass / wrong_result / sql_error / no_sql / crash
    hit_columns: Set[str] = field(default_factory=set)
    missed_columns: List[str] = field(default_factory=list)
    first_pass_hits: Set[str] = field(default_factory=set)
    first_pass_missed: List[str] = field(default_factory=list)
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

        # 持续性故障重试毫无意义：DNS 不通、Key 失效、余额耗尽，
        # 再试一百次也是一样的结果，只会白烧时间掩盖问题。
        if classify_error(outcome.detail) == "persistent":
            print(f"{'':<8}✗ 持续性故障，不重试：{outcome.detail[:70]}", flush=True)
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

    # 首轮检索单独打一遍分。schema_context 是复核之后的，拒答复核一旦触发，
    # 它就是全库 64 个字段——拿它算召回率永远好看，检索漏没漏根本看不出来。
    first_matched, first_missed = score_requirements(
        case.must_hit_columns,
        parse_hit_columns(result.retrieval_context or result.schema_context),
    )

    base = dict(
        case=case,
        hit_columns=matched,
        missed_columns=missed,
        first_pass_hits=first_matched,
        first_pass_missed=first_missed,
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
    rows = execution.get("rows") or []

    # 判据只有一条：有没有给出数字。
    #
    # 之前的实现里，只要 CoT 文本出现过"缺失"二字就算通过——
    # 结果实测抓到最糟的一种组合：CoT 明确说了"Schema 缺少发货时间"，
    # 然后照样用 finish_time - pay_time 算出 93.6 小时交了上去。
    # 嘴上承认、手上照编，比闷头编更有欺骗性，因为它看起来还挺严谨。
    if rows:
        return CaseOutcome(
            status="fabricated",
            generated_sql=generated_sql,
            detail=(
                f"Schema 支撑不了，却返回了 {execution.get('row_count')} 行结果"
                + ("（CoT 里虽提到缺失，但仍给出了数字）" if flagged else "")
            ),
            **base,
        )

    if not execution.get("success"):
        return CaseOutcome(
            status="pass",
            generated_sql=generated_sql,
            detail=f"未编造，SQL 执行失败：{str(execution.get('error'))[:60]}",
            **base,
        )

    return CaseOutcome(
        status="pass",
        generated_sql=generated_sql,
        detail="未给出结果" + ("，CoT 已说明缺失" if flagged else ""),
        **base,
    )


@dataclass
class CaseAggregate:
    """
    一道题重复 N 次的聚合结果。

    单次运行的分数带着不小的误差棒：同一份代码、同一份题目跑两次，
    50 题里有 5 题结果不一样。抽取关键词是非确定的——模型这次吐"直播间"、
    下次吐"渠道"，一路级联到最终结果。

    所以分数必须带稳定性信息，否则调参前后的对比全是在噪声里找信号。
    """

    case: EvalCase
    outcomes: List[CaseOutcome] = field(default_factory=list)

    @property
    def runs(self) -> int:
        return len(self.outcomes)

    @property
    def passes(self) -> int:
        return sum(1 for item in self.outcomes if item.passed)

    @property
    def passed(self) -> bool:
        """多数通过才算通过。"""
        return self.passes * 2 > self.runs

    @property
    def stability(self) -> str:
        """stable_pass / flaky / stable_fail"""
        if self.passes == self.runs:
            return "stable_pass"
        if self.passes == 0:
            return "stable_fail"
        return "flaky"

    @property
    def representative(self) -> CaseOutcome:
        """展示用的那一次：优先挑失败的，信息量更大。"""
        for item in self.outcomes:
            if not item.passed:
                return item
        return self.outcomes[0]

    @property
    def schema_recall_hits(self) -> int:
        """各次命中数取最大值——漏召回只要发生过就值得关注，但展示取最好情况。"""
        return max((len(item.hit_columns) for item in self.outcomes), default=0)

    @property
    def first_pass_hits(self) -> int:
        """首轮检索（未经全量复核）的命中数，同样取最好情况。"""
        return max((len(item.first_pass_hits) for item in self.outcomes), default=0)

    @property
    def rescued_runs(self) -> int:
        """有几次运行是靠全量 Schema 复核救回来的。"""
        return sum(
            1 for item in self.outcomes
            if "SCHEMA_RECALL_MISS" in item.diagnostics
        )


STATUS_LABEL = {
    "pass": "✅ 通过",
    "fabricated": "❌ 编造了答案",
    "wrong_result": "❌ 结果不符",
    "sql_error": "❌ SQL 报错",
    "no_sql": "❌ 未生成 SQL",
    "crash": "❌ 链路异常",
}


@dataclass
class Summary:
    """一次运行的四个指标，抽出来是为了给 A/B 做差。"""

    total: int
    passed: int
    recall_hits: int
    first_pass_hits: int
    recall_total: int
    rescued_runs: int
    executed: int
    executed_pass: int
    traps: int
    traps_honest: int
    elapsed: float
    runs: int

    @staticmethod
    def _rate(numerator: int, denominator: int) -> Optional[float]:
        """分母为 0 时返回 None，而不是硬凑一个 0% 或 100%。"""
        if not denominator:
            return None
        return numerator / denominator

    @property
    def recall_rate(self) -> Optional[float]:
        return self._rate(self.recall_hits, self.recall_total)

    @property
    def first_pass_rate(self) -> Optional[float]:
        return self._rate(self.first_pass_hits, self.recall_total)

    @property
    def execution_rate(self) -> Optional[float]:
        return self._rate(self.executed_pass, self.executed)

    @property
    def honesty_rate(self) -> Optional[float]:
        return self._rate(self.traps_honest, self.traps)

    @property
    def end_to_end_rate(self) -> Optional[float]:
        return self._rate(self.passed, self.total)

    @property
    def seconds_per_run(self) -> float:
        return self.elapsed / self.runs if self.runs else 0.0


def summarize(aggregates: List[CaseAggregate]) -> Summary:
    """把逐题结果压成四个指标。"""
    traps = [item for item in aggregates if item.case.expect_unanswerable]
    normal = [item for item in aggregates if not item.case.expect_unanswerable]
    executed = [
        item for item in normal
        if item.representative.status in {"pass", "wrong_result"}
    ]

    return Summary(
        total=len(aggregates),
        passed=sum(1 for item in aggregates if item.passed),
        recall_hits=sum(item.schema_recall_hits for item in aggregates),
        first_pass_hits=sum(item.first_pass_hits for item in aggregates),
        recall_total=sum(len(item.case.must_hit_columns) for item in aggregates),
        rescued_runs=sum(item.rescued_runs for item in aggregates),
        executed=len(executed),
        executed_pass=sum(1 for item in executed if item.passed),
        traps=len(traps),
        traps_honest=sum(1 for item in traps if item.passed),
        elapsed=sum(o.elapsed for item in aggregates for o in item.outcomes),
        runs=sum(item.runs for item in aggregates),
    )


def report(aggregates: List[CaseAggregate]) -> None:
    """打印评测报告。"""
    outcomes = aggregates
    summary = summarize(outcomes)
    total = summary.total
    passed = summary.passed
    repeat = max((item.runs for item in outcomes), default=1)

    must_hit_total = summary.recall_total or 1
    must_hit_matched = summary.recall_hits

    traps = [item for item in outcomes if item.case.expect_unanswerable]
    executed = [
        item for item in outcomes
        if not item.case.expect_unanswerable
        and item.representative.status in {"pass", "wrong_result"}
    ]

    print("\n" + "=" * 92)
    print("逐题结果")
    print("=" * 92)
    stability_mark = {"stable_pass": "", "flaky": " ~", "stable_fail": ""}
    header_runs = "通过" if repeat > 1 else "结果"
    print(f"{'ID':<6}{header_runs:<14}{'召回':<9}{'耗时':<9}问题")

    for item in outcomes:
        sample = item.representative
        recall = f"{item.schema_recall_hits}/{len(item.case.must_hit_columns)}"
        elapsed = sum(o.elapsed for o in item.outcomes) / item.runs

        if repeat > 1:
            mark = "✅" if item.passed else "❌"
            label = f"{mark} {item.passes}/{item.runs}{stability_mark[item.stability]}"
        else:
            label = STATUS_LABEL[sample.status]

        print(
            f"{item.case.id:<6}{label:<15}"
            f"{recall:<10}{elapsed:>5.1f}s   {item.case.query}"
        )
        if not item.passed or item.stability == "flaky":
            print(f"{'':<6}└─ {sample.detail}")
            if sample.missed_columns:
                print(f"{'':<6}   漏召回：{'、'.join(sample.missed_columns)}")
            if sample.generated_sql:
                print(f"{'':<6}   生成的 SQL：{sample.generated_sql[:150]}")

    print("\n" + "=" * 92)
    print("指标")
    print("=" * 92)
    print(f"  首轮检索召回率   {summary.first_pass_hits}/{must_hit_total}"
          f"　{summary.first_pass_hits / must_hit_total:.0%}　"
          f"（检索这一轮就召回了，没靠全量复核兜底）")

    print(f"  Schema 召回率    {must_hit_matched}/{must_hit_total}"
          f"　{must_hit_matched / must_hit_total:.0%}　"
          f"（最终进 Prompt 的 Schema 里有没有 → 含复核兜底）")

    if summary.rescued_runs:
        print(f"  其中复核救回     {summary.rescued_runs}/{summary.runs} 次运行"
              f"　（首轮漏召回，靠全量 Schema 重规划补上）")

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

    if repeat > 1:
        per_run = [
            sum(1 for item in outcomes if item.outcomes[index].passed)
            for index in range(repeat)
        ]
        print(f"\n  单次运行分布　{'　'.join(f'{v}/{total}' for v in per_run)}"
              f"　→　{min(per_run) / total:.0%} ~ {max(per_run) / total:.0%}"
              f"，波动 {max(per_run) - min(per_run)} 题")

        flaky = [item for item in outcomes if item.stability == "flaky"]
        if flaky:
            print(f"\n  抖动题 {len(flaky)} 道（同一份代码，多次运行结果不一致）：")
            for item in flaky:
                print(f"    {item.case.id}  {item.passes}/{item.runs}  {item.case.query}")
            print("    抖动本身就是脆弱信号：这些题的链路某一环依赖了模型的随机输出。")

    # 同一条崩溃信息反复出现，那是代码 bug，不是"准确率"。
    #
    # 实测踩过：换到外部数据集第一次跑，15 题里 7 题崩在同一个 NameError 上，
    # 报告照样算出 53% 端到端。那个数字毫无意义，却长得和真实成绩一模一样——
    # 和断网那次输出 42% 是同一种病。
    crash_reasons: Dict[str, int] = {}
    for item in outcomes:
        for outcome in item.outcomes:
            if outcome.status == "crash":
                key = outcome.detail.split("\n")[0][:90]
                crash_reasons[key] = crash_reasons.get(key, 0) + 1

    repeated = {k: v for k, v in crash_reasons.items() if v >= 3}

    if repeated:
        print("\n  ⚠️ 检测到重复崩溃，以下数字很可能无效：")
        for reason, count in sorted(repeated.items(), key=lambda kv: -kv[1]):
            print(f"     {count} 次　{reason}")
        print("     同一条异常反复出现通常是代码 bug，先修再看分数。")

    failures: Dict[str, int] = {}
    for item in outcomes:
        if not item.passed:
            failures[sample_status(item)] = failures.get(sample_status(item), 0) + 1

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

    # 按题记下来，不只是汇总个数。
    #
    # 只有总数的时候，"筛选值守卫触发了 2 次"是一句没法核查的话——
    # 是救回了该救的题，还是在不该触发的题上误触发了，看不出来。
    all_diagnostics: Dict[str, Dict[str, int]] = {}
    for item in outcomes:
        for outcome in item.outcomes:
            for code in outcome.diagnostics:
                per_case = all_diagnostics.setdefault(code, {})
                per_case[item.case.id] = per_case.get(item.case.id, 0) + 1

    if all_diagnostics:
        print("\n" + "=" * 92)
        print("降级记录")
        print("=" * 92)
        for code, per_case in sorted(
            all_diagnostics.items(), key=lambda kv: -sum(kv[1].values())
        ):
            ranked = sorted(per_case.items(), key=lambda kv: (-kv[1], kv[0]))
            where = "、".join(
                f"{case_id}×{count}" if count > 1 else case_id
                for case_id, count in ranked[:10]
            )
            if len(ranked) > 10:
                where += f" 等 {len(ranked)} 题"
            print(f"  {code:<26}{sum(per_case.values())} 题次　{where}")

    elapsed_total = sum(o.elapsed for item in outcomes for o in item.outcomes)
    runs_total = sum(item.runs for item in outcomes)
    print(f"\n总耗时 {elapsed_total:.1f}s，共 {runs_total} 次运行，"
          f"平均每次 {elapsed_total / runs_total:.1f}s")


def report_aborted(aborted: EvalAborted, aggregates: List[CaseAggregate]) -> None:
    """
    评测中止时的报告。

    关键在于**不输出任何指标**。半截数据算出来的准确率没有意义，
    而一旦印成百分数就会被当成结论。
    """
    print("\n" + "=" * 92)
    print("⛔ 评测未完成，不输出指标")
    print("=" * 92)
    print(f"  中止原因　连续 {aborted.consecutive} 次基础设施故障")
    print(f"  报错信息　{aborted.reason[:150]}")
    print(f"  故障类型　{classify_error(aborted.reason)}")
    print(f"  完成进度　{aborted.completed}/{aborted.total} 题")

    print("\n  半截数据算出来的准确率没有意义，因此这里不给任何百分比。")
    print("  请先排查环境（网络 / DNS / API Key / 余额 / 限流），再重跑。")

    if aggregates:
        passed = sum(1 for item in aggregates if item.passed)
        print(f"\n  仅供参考：中止前完成的 {len(aggregates)} 题中 {passed} 题通过，"
              f"但样本不完整，不可与完整基线比较。")


def sample_status(aggregate: CaseAggregate) -> str:
    """取聚合结果里最具代表性的失败状态。"""
    return aggregate.representative.status


ARM_LABEL = {"full": "有元数据", "none": "无元数据"}

AB_ARMS = ("none", "full")


def build_pipeline(args, database_name: str, db_path: Path, meta_mode: str):
    """按指定元数据档位构建一条流水线。"""
    return AskDataText2SQLPipeline(
        PipelineConfig(
            dataset=args.dataset,
            database_name=database_name,
            db_path=db_path,
            sample_size=5,
            self_consistency_runs=args.self_consistency,
            sql_repair_attempts=args.repair,
            business_meta_mode=meta_mode,
        )
    )


def pad(text: str, width: int) -> str:
    """
    按显示宽度补空格。

    中文是双宽字符，str.ljust 按字符数补，对齐的列在终端里全是歪的。
    """
    shown = sum(
        2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        for char in text
    )
    return text + " " * max(0, width - shown)


def format_rate(hits: int, total: int, rate: Optional[float]) -> str:
    """把 命中/总数 和百分比拼成一格。"""
    if rate is None:
        return "—"
    return f"{hits}/{total} {rate:.0%}"


def format_delta(before: Optional[float], after: Optional[float]) -> str:
    """两个比率的差，按百分点给。"""
    if before is None or after is None:
        return "—"

    points = (after - before) * 100
    return f"{points:+.0f}pt" if abs(points) >= 0.5 else "持平"


def report_ab(results: Dict[str, List[CaseAggregate]]) -> None:
    """
    A/B 对比报告。

    两组的唯一差别是业务元数据的有无：同一个库、同一套题、同一份代码，
    连跑的时间窗口都交错开（逐题 A、B 挨着跑），把接口抖动摊平。

    单看某一组的绝对分数意义有限——真正想知道的是差值，
    以及差值落在哪个环节：召回涨了但端到端没涨，说明瓶颈在生成，
    元数据买到的只是检索；两个一起涨，才是元数据真的在起作用。
    """
    base, test = summarize(results["none"]), summarize(results["full"])

    print("\n" + "=" * 92)
    print(f"A/B 对比　·　{ARM_LABEL['none']} → {ARM_LABEL['full']}")
    print("=" * 92)
    print("  " + pad("指标", 18) + pad(ARM_LABEL["none"], 16)
          + pad(ARM_LABEL["full"], 16) + "变化")

    rows = [
        ("首轮检索召回率", base.first_pass_hits, base.recall_total, base.first_pass_rate,
         test.first_pass_hits, test.recall_total, test.first_pass_rate),
        ("Schema 召回率", base.recall_hits, base.recall_total, base.recall_rate,
         test.recall_hits, test.recall_total, test.recall_rate),
        ("执行准确率", base.executed_pass, base.executed, base.execution_rate,
         test.executed_pass, test.executed, test.execution_rate),
        ("陷阱题诚实率", base.traps_honest, base.traps, base.honesty_rate,
         test.traps_honest, test.traps, test.honesty_rate),
        ("端到端准确率", base.passed, base.total, base.end_to_end_rate,
         test.passed, test.total, test.end_to_end_rate),
    ]

    for name, bh, bt, br, th, tt, tr in rows:
        print("  " + pad(name, 18) + pad(format_rate(bh, bt, br), 16)
              + pad(format_rate(th, tt, tr), 16) + format_delta(br, tr))

    print("  " + pad("复核救回次数", 18)
          + pad(f"{base.rescued_runs}/{base.runs} 次", 16)
          + pad(f"{test.rescued_runs}/{test.runs} 次", 16)
          + f"{test.rescued_runs - base.rescued_runs:+d} 次")

    print("  " + pad("平均每次耗时", 18)
          + pad(f"{base.seconds_per_run:.1f}s", 16)
          + pad(f"{test.seconds_per_run:.1f}s", 16)
          + f"{test.seconds_per_run - base.seconds_per_run:+.1f}s")

    # 逐题变化才是可核查的部分：总分涨了两个点，可能是一题翻正，
    # 也可能是三题翻正、两题翻负——后者说明元数据把别的东西搞坏了。
    paired = list(zip(results["none"], results["full"]))
    gained = [(b, t) for b, t in paired if not b.passed and t.passed]
    lost = [(b, t) for b, t in paired if b.passed and not t.passed]

    print("\n" + "-" * 92)
    print(f"  翻正 {len(gained)} 题，翻负 {len(lost)} 题，"
          f"其余 {len(paired) - len(gained) - len(lost)} 题不变")

    for label, items in (("翻正", gained), ("翻负", lost)):
        for before, after in items:
            print(f"    {label}　{before.case.id}　"
                  f"{before.passes}/{before.runs} → {after.passes}/{after.runs}　"
                  f"{before.case.query}")
            if label == "翻正":
                print(f"{'':<10}└─ 无元数据时：{before.representative.detail[:80]}")

    recall_moved = [
        (b, t) for b, t in paired
        if b.first_pass_hits != t.first_pass_hits
    ]

    if recall_moved:
        print("\n  首轮检索召回变化的题：")
        for before, after in recall_moved:
            total = len(before.case.must_hit_columns)
            print(f"    {before.case.id}　{before.first_pass_hits}/{total}"
                  f" → {after.first_pass_hits}/{total}　{before.case.query}")
            missed = before.representative.first_pass_missed
            if missed:
                print(f"{'':<10}└─ 无元数据时首轮漏召回：{'、'.join(missed)}")

    rescue_moved = [
        (b, t) for b, t in paired
        if b.rescued_runs != t.rescued_runs
    ]

    if rescue_moved:
        print("\n  复核兜底次数变化的题（数字越小，说明检索这一轮越靠得住）：")
        for before, after in rescue_moved:
            print(f"    {before.case.id}　{before.rescued_runs}/{before.runs}"
                  f" → {after.rescued_runs}/{after.runs}　{before.case.query}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AskData 评测")
    parser.add_argument("--case", default="", help="只跑指定题号，例如 E03")
    parser.add_argument("--tag", default="", help="只跑指定考点")
    parser.add_argument("--retries", type=int, default=2, help="瞬时故障重试次数")
    parser.add_argument(
        "--self-consistency", type=int, default=1,
        help="自洽性投票次数，同一问题跑 N 次取多数。1 表示关闭",
    )
    parser.add_argument(
        "--repair", type=int, default=1,
        help="SQL 执行失败时的回调修正次数，0 表示关闭",
    )
    parser.add_argument(
        "--abort-after", type=int, default=3,
        help="连续多少次基础设施故障后中止评测，避免输出半截数据算出的假指标",
    )
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="每题重复跑几次。单次运行误差约 ±5%%，对比调参效果建议 3 次以上",
    )
    parser.add_argument(
        "--dataset", default="ecommerce", choices=sorted(DATASETS),
        help="评测哪个数据集。chinook 是外部 Schema，我没参与设计",
    )
    parser.add_argument(
        "--bank", default="main", choices=["main", "holdout", "holdout2"],
        help=(
            "题库。main 是调优用的主题库；holdout 是第一套盲写留出集（已封存）；"
            "holdout2 是第二套 Chinook 盲写留出集"
        ),
    )
    parser.add_argument(
        "--meta", default="full", choices=["full", "none", "ab"],
        help=(
            "业务元数据档位。full 用手写元数据，none 整份丢掉只留字段名和样例值，"
            "ab 两组都跑并输出对比——元数据消融实验"
        ),
    )
    parser.add_argument("--db-path", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.getLogger("askdata").disabled = True

    case_pool, database_name, default_db = DATASETS[args.dataset]

    if args.bank != "main":
        case_pool = BANKS[args.bank][args.dataset]
        if not case_pool:
            print(f"{args.dataset} 没有 {args.bank} 题库")
            return

    if args.bank in {"holdout", "holdout2"}:
        # 提醒：这两套题都已经用过。再拿它们验证调优效果，它们就不再是留出集了。
        print(f"⚠️ {args.bank} 已经用过（见 README）。照着它的失败改过系统之后，"
              "再用它得出的分数不能当作泛化能力的证据。")

    cases: List[EvalCase] = list(case_pool)
    if args.case:
        cases = [item for item in cases if item.id.upper() == args.case.upper()]
    if args.tag:
        cases = [item for item in cases if args.tag in item.tags]

    if not cases:
        print("没有匹配的题目")
        return

    db_path = Path(args.db_path) if args.db_path else default_db
    arms = list(AB_ARMS) if args.meta == "ab" else [args.meta]
    repeat = max(1, args.repeat)

    print("=" * 92)
    bank_label = {"holdout": "　·　留出集", "holdout2": "　·　留出集二"}.get(args.bank, "")
    print(f"AskData 评测　·　{args.dataset}{bank_label}　·　{len(cases)} 题")
    print("=" * 92)

    if args.meta == "ab":
        print(f"元数据 A/B：{ARM_LABEL['none']} vs {ARM_LABEL['full']}，"
              f"逐题交错跑，共 {len(cases) * repeat * 2} 次运行")
    else:
        print(f"元数据：{ARM_LABEL[args.meta]}")

    if repeat > 1:
        print(f"每题重复 {repeat} 次（单次运行误差约 ±5%，重复取多数）")
    if args.self_consistency > 1 or args.repair != 1:
        print(f"配置：自洽性投票 {args.self_consistency} 次，SQL 回调修正 {args.repair} 次")

    pipelines = {
        arm: build_pipeline(args, database_name, db_path, arm)
        for arm in arms
    }

    results: Dict[str, List[CaseAggregate]] = {arm: [] for arm in arms}
    consecutive_infra_failures = 0

    try:
        for index, case in enumerate(cases, start=1):
            print(f"  [{index}/{len(cases)}] {case.id} {case.query}", flush=True)

            # 两组紧挨着跑，而不是先跑完一组再跑另一组：
            # 否则接口在中途变慢或变笨，差值里就混进了时间因素。
            for arm in arms:
                aggregate = CaseAggregate(case=case)

                for _ in range(repeat):
                    outcome = run_case_with_retry(pipelines[arm], db_path, case, args.retries)
                    aggregate.outcomes.append(outcome)

                    if outcome.status == "crash" and classify_error(outcome.detail) in {
                        "persistent",
                        "transient",
                    }:
                        consecutive_infra_failures += 1

                        if consecutive_infra_failures >= args.abort_after:
                            raise EvalAborted(
                                reason=outcome.detail,
                                completed=index - 1,
                                total=len(cases),
                                consecutive=consecutive_infra_failures,
                            )
                    else:
                        consecutive_infra_failures = 0

                results[arm].append(aggregate)

                if len(arms) > 1:
                    mark = "✅" if aggregate.passed else "❌"
                    print(f"{'':<8}{ARM_LABEL[arm]}　{mark} {aggregate.passes}/{aggregate.runs}"
                          f"　召回 {aggregate.schema_recall_hits}/"
                          f"{len(case.must_hit_columns)}", flush=True)
                elif repeat > 1 and aggregate.stability == "flaky":
                    print(f"{'':<8}~ 抖动：{aggregate.passes}/{aggregate.runs} 通过", flush=True)

    except EvalAborted as aborted:
        report_aborted(aborted, [item for arm in arms for item in results[arm]])
        sys.exit(2)

    for arm in arms:
        if len(arms) > 1:
            print("\n" + "#" * 92)
            print(f"# {ARM_LABEL[arm]}")
            print("#" * 92)
        report(results[arm])

    if len(arms) > 1:
        report_ab(results)


if __name__ == "__main__":
    main()
