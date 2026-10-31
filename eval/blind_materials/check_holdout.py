"""
盲写题冻结前的机械校验和去重。只输出题号和检查项——不打印题目内容（问题、SQL、字段、结果），
SQL 报错只打印异常类型：跑校验的人在冻结前不该看到题。

    python eval/blind_materials/check_holdout.py <出题目录> --module cases_holdout9 --var HOLDOUT9_SAKILA_CASES \\
        --dataset sakila --prefix H9S --count 40 --traps 4 --min-hard 14 --max-easy 4 --min-tables 13

多轮追问（列表里是 MultiTurnCase）：--count 是组数，--traps 是陷阱轮数，难度分布不查（--min-hard 0 --max-easy 99）：

    python eval/blind_materials/check_holdout.py <出题目录> --module cases_multiturn1 --var MULTITURN1_ECOMMERCE_CASES \\
        --dataset ecommerce --prefix M1E --count 12 --traps 2 --min-hard 0 --max-easy 99 --min-tables 8 --min-form 3

原先这份脚本只放在会话的临时目录里（第四到八套各一份，逐套改），被系统清理掉了；第九套起收进仓库。

检查项：
- 题号：前缀、数量、不重复、不和已有题库撞
- 参考 SQL 跑得通；非陷阱题结果不退化（不是 0 行，也不是单个 0 或 NULL）
- 陷阱题配置：SELECT 1 WHERE 0、必中字段为空、带"陷阱题"标签，数量对
- 必中字段真实存在（候选列表里每一项都要存在）
- 候选路径（alt_sql.json）跑得通，结果和参考答案一致
- TopN 不并列：ORDER BY … LIMIT N 的，排序依据是输出列就比第 N、N+1 行，不是就报"无法机械判定"；
  组内取前 N（ROW_NUMBER）的，换成 RANK 结果行数变了就是有并列
- 参考 SQL 输出列用了 ROUND，题面要写明保留几位小数
- 题面不出现表名、字段名；难度分布；带指定考点的非陷阱题过半；标了多表连接的至少用到 4 张表；表覆盖
- 去重：和全部已有题库（含探针）以及这一套自己的其他题比，问法相似度 >= 0.6 或参考答案结果集相同；多轮追问只比第 1 轮
- 多轮追问的结构：每组 3–4 轮、轮的题号是 组号-轮次、第 1 轮不是陷阱也不标追问形式、每轮追问标了规范里的形式、
  每组至少两种形式、陷阱轮的下一轮标了跨轮、指代的上一轮不超过 10 行、每种形式的次数、至少 2 组跨轮
"""

from __future__ import annotations

import argparse
import difflib
import importlib
import itertools
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.runner import BANKS, DATASETS, case_ndigits, rows_match  # noqa: E402

TRAP_SQL = "SELECT 1 WHERE 0"
HARD_TAGS = {"考点:多表连接", "考点:两层聚合", "考点:窗口排名", "考点:相对时间", "考点:否定集合"}
SIMILAR = 0.6

problems: list = []


def fail(case_id: str, check: str, extra: str = "") -> None:
    problems.append((case_id, check, extra))


def run(conn: sqlite3.Connection, sql: str) -> list:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql)]


def degenerate(rows: list) -> bool:
    if not rows:
        return True
    if len(rows) == 1 and len(rows[0]) == 1:
        value = next(iter(rows[0].values()))
        return value is None or value == 0
    return False


def topn_problem(conn, sql: str) -> str:
    """返回空串表示没问题；否则返回检查项。"""
    window = re.search(r"ROW_NUMBER\s*\(\s*\)", sql, re.I)
    if window:
        try:
            if len(run(conn, sql)) != len(run(conn, re.sub(r"ROW_NUMBER\s*\(\s*\)", "RANK()", sql, flags=re.I))):
                return "组内前 N 有并列（换成 RANK 行数变了）"
        except sqlite3.Error:
            return "组内前 N 无法机械判定（换成 RANK 跑不通）"
    match = re.search(r"ORDER\s+BY\s+(.+?)\s+LIMIT\s+(\d+)\s*;?\s*$", sql, re.I | re.S)
    if not match:
        return ""
    order_expr, n = match.group(1), int(match.group(2))
    first_key = re.sub(r"\s+(ASC|DESC)\s*$", "", order_expr.split(",")[0].strip(), flags=re.I)
    rows = run(conn, sql[:match.start(2)] + str(n + 1) + sql[match.end(2):])
    if len(rows) <= n:
        return ""
    columns = list(rows[0])
    key = first_key.split(".")[-1].strip('"`[]')
    if key in columns:
        column = key
    elif key.isdigit() and 1 <= int(key) <= len(columns):
        column = columns[int(key) - 1]
    else:
        return "TopN 并列无法机械判定（ORDER BY 不是输出列）"
    return "TopN 第 N 名和第 N+1 名并列" if rows[n - 1][column] == rows[n][column] else ""


FOLLOW_UP_FORMS = ("追问:指代", "追问:省略", "追问:加条件", "追问:换角度", "追问:跨轮", "追问:依赖结果")
MAX_REFERRED_ROWS = 10


def check_chains(chains: list, results: dict, dataset: str, min_form: int) -> None:
    """多轮追问的结构：轮数、轮的题号、第 1 轮自包含、追问标了形式、陷阱轮之后指回更早的轮、形式的分布。"""
    form_counts: dict = {}
    cross_chains = 0
    for chain in chains:
        turns = chain.turns
        if not 3 <= len(turns) <= 4:
            fail(chain.id, f"轮数 {len(turns)}，应为 3 或 4")
        for index, turn in enumerate(turns, start=1):
            if turn.id != f"{chain.id}-{index}":
                fail(turn.id, "轮的题号应为 组号-轮次")
        if turns and turns[0].expect_unanswerable:
            fail(turns[0].id, "第 1 轮不能是陷阱轮")
        if turns and any(tag.startswith("追问:") for tag in turns[0].tags):
            fail(turns[0].id, "第 1 轮不该标追问形式")
        used: set = set()
        for previous, turn in zip(turns, turns[1:]):
            forms = [tag for tag in turn.tags if tag.startswith("追问:")]
            if not forms:
                fail(turn.id, "追问没有标形式")
            if set(forms) - set(FOLLOW_UP_FORMS):
                fail(turn.id, "追问形式不在规范列出的六种里")
            used.update(forms)
            if previous.expect_unanswerable and "追问:跨轮" not in forms:
                fail(turn.id, "陷阱轮的下一轮要指回更早的轮（追问:跨轮）")
            if "追问:指代" in forms and len(results.get(previous.id) or []) > MAX_REFERRED_ROWS:
                fail(turn.id, f"指代的上一轮结果超过 {MAX_REFERRED_ROWS} 行")
        if len(turns) > 1 and len(used) < 2:
            fail(chain.id, "这一组的追问只用了一种形式")
        for form in used:
            form_counts[form] = form_counts.get(form, 0) + sum(form in t.tags for t in turns)
        cross_chains += "追问:跨轮" in used
    for form in FOLLOW_UP_FORMS:
        if form_counts.get(form, 0) < min_form:
            fail(dataset, f"{form} 出现 {form_counts.get(form, 0)} 次，至少 {min_form} 次")
    if cross_chains < 2:
        fail(dataset, f"带 追问:跨轮 的组 {cross_chains} 个，至少 2 个")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("writer_dir")
    parser.add_argument("--module", required=True)
    parser.add_argument("--var", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--traps", type=int, required=True)
    parser.add_argument("--min-hard", type=int, required=True)
    parser.add_argument("--max-easy", type=int, required=True)
    parser.add_argument("--min-tables", type=int, required=True)
    parser.add_argument("--self-bank", default="", help="评测器里这一套的题库名，去重时跳过它自己")
    parser.add_argument("--min-form", type=int, default=2, help="多轮追问：每种追问形式至少出现几次")
    args = parser.parse_args()

    writer_dir = Path(args.writer_dir)
    sys.path.insert(0, str(writer_dir))
    cases = getattr(importlib.import_module(args.module), args.var)
    # 多轮追问：一组是一个 MultiTurnCase。逐题的检查摊平成一轮一轮做，组的结构另外查
    chains = cases if cases and hasattr(cases[0], "turns") else []
    if chains:
        cases = [turn for chain in chains for turn in chain.turns]
    units = chains or cases
    alt_path = writer_dir / "alt_sql.json"
    alt = json.loads(alt_path.read_text(encoding="utf-8")) if alt_path.exists() else {}
    db_path = ROOT / DATASETS[args.dataset][2]
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    columns_by_table = {t: [row[1] for row in conn.execute(f'PRAGMA table_info("{t}")')] for t in tables}

    # ---- 题号
    ids = [c.id for c in units] + ([c.id for c in cases] if chains else [])
    if len(units) != args.count:
        fail(args.dataset, f"{'组' if chains else '题'}数 {len(units)}，应为 {args.count}")
    if len(set(ids)) != len(ids):
        fail(args.dataset, "题号重复")
    for c in units:
        if not re.fullmatch(rf"{args.prefix}\d\d", c.id):
            fail(c.id, "题号格式不对")
    existing = {case.id for bank, banks in BANKS.items() if bank != args.self_bank for pool in banks.values() for case in pool} | \
               {case.id for pool, _, _ in DATASETS.values() for case in pool}
    for c in units:
        if c.id in existing:
            fail(c.id, "题号和已有题库撞了")

    # ---- 逐题
    results = {}
    touched = set()
    traps = [c for c in cases if c.expect_unanswerable]
    if len(traps) != args.traps:
        fail(args.dataset, f"陷阱题 {len(traps)} 道，应为 {args.traps}")
    for c in cases:
        if c.expect_unanswerable:
            if c.reference_sql.strip() != TRAP_SQL or c.must_hit_columns or "陷阱题" not in c.tags:
                fail(c.id, "陷阱题配置不对")
            continue
        if "陷阱题" in c.tags:
            fail(c.id, "标了陷阱题却不是 expect_unanswerable")
        try:
            rows = run(conn, c.reference_sql)
        except sqlite3.Error as exc:
            fail(c.id, "参考 SQL 跑不通", type(exc).__name__)
            continue
        results[c.id] = rows
        if degenerate(rows):
            fail(c.id, "结果退化（0 行或单个 0/NULL）")
        for item in c.must_hit_columns:
            for name in (item if isinstance(item, list) else [item]):
                table, _, column = name.partition(".")
                if column not in columns_by_table.get(table, []):
                    fail(c.id, "必中字段不存在")
        problem = topn_problem(conn, c.reference_sql)
        if problem:
            fail(c.id, problem)
        rounded = re.findall(r"ROUND\s*\([^;]*?,\s*(\d)\s*\)", c.reference_sql, re.I)
        if rounded and not re.search(r"(保留|精确到|四舍五入到)\s*[0-9一两二三四]\s*位", c.query):
            fail(c.id, "参考 SQL 用了 ROUND，题面没写保留几位小数（只用于比较条件时请核实）")
        for sql in alt.get(c.id, []):
            try:
                alt_rows = run(conn, sql)
            except sqlite3.Error as exc:
                fail(c.id, "候选路径 SQL 跑不通", type(exc).__name__)
                continue
            if not rows_match(alt_rows, results[c.id], c.ordered, case_ndigits(c)):
                fail(c.id, "候选路径结果和参考答案不一致")
        used = {t for t in tables if re.search(rf"\b{re.escape(t)}\b", c.reference_sql)}
        touched |= used
        if "考点:多表连接" in c.tags and len(used) < 4:
            fail(c.id, "标了多表连接，参考 SQL 用到的表不到 4 张")

    # ---- 整套
    identifiers = set(tables) | {col for cols in columns_by_table.values() for col in cols}
    for c in cases:
        leaked = [n for n in identifiers if re.search(rf"(?<![A-Za-z0-9_]){re.escape(n)}(?![A-Za-z0-9_])", c.query)]
        if leaked:
            fail(c.id, f"题面出现了表名或字段名 {len(leaked)} 个")
    real = [c for c in cases if not c.expect_unanswerable]
    if chains:
        check_chains(chains, results, args.dataset, args.min_form)
        # 去重只看第 1 轮：追问离不开上下文，单拿出来和别的题比没有意义
        real = [chain.turns[0] for chain in chains if chain.turns and not chain.turns[0].expect_unanswerable]
    else:
        hard = sum("难度:难" in c.tags for c in real)
        easy = sum("难度:简单" in c.tags for c in real)
        if hard < args.min_hard or easy > args.max_easy:
            fail(args.dataset, f"难度分布不达标：难 {hard}（至少 {args.min_hard}）、简单 {easy}（至多 {args.max_easy}）")
        tagged = sum(bool(HARD_TAGS & set(c.tags)) for c in real)
        if tagged * 2 < len(real):
            fail(args.dataset, f"带指定考点的非陷阱题 {tagged}/{len(real)}，不到一半")
    if len(touched) < args.min_tables:
        fail(args.dataset, f"参考 SQL 只覆盖了 {len(touched)} 张表，至少 {args.min_tables} 张")

    # ---- 去重：已有题库（含探针，跳过自己）+ 这一套内部
    old = [(f"{bank}:{case.id}", case) for bank, banks in BANKS.items() if bank != args.self_bank
           for case in banks.get(args.dataset) or []]
    old += [(f"main:{case.id}", case) for case in DATASETS[args.dataset][0]]
    dups = []
    for c in real:
        for label, other in old:
            ratio = difflib.SequenceMatcher(None, c.query, other.query).ratio()
            same = False
            if not other.expect_unanswerable:
                try:
                    same = c.id in results and rows_match(run(conn, other.reference_sql), results[c.id], c.ordered, case_ndigits(c))
                except sqlite3.Error:
                    pass
            if ratio >= SIMILAR or same:
                dups.append((c.id, label, ratio, same))
    for a, b in itertools.combinations(real if chains else cases, 2):
        ratio = difflib.SequenceMatcher(None, a.query, b.query).ratio()
        same = a.id in results and b.id in results and rows_match(results[a.id], results[b.id], a.ordered, case_ndigits(a))
        if ratio >= SIMILAR or same:
            dups.append((b.id, f"本套:{a.id}", ratio, same))
    conn.close()

    print(f"题数 {len(cases)}（陷阱 {len(traps)}）；候选路径 SQL {sum(len(v) for v in alt.values())} 条；"
          f"参考 SQL 覆盖 {len(touched)}/{len(tables)} 张表")
    print(f"\n机械校验问题 {len(problems)} 处：")
    for case_id, check, extra in problems:
        print(f"  {case_id:10} {check} {extra}")
    print(f"\n去重标记 {len(dups)} 处（相似度 >= {SIMILAR} 或结果集完全相同）：")
    for case_id, label, ratio, same in dups:
        print(f"  {case_id}  撞 {label:14} 相似度 {ratio:.2f}  结果集{'相同' if same else '不同'}")


if __name__ == "__main__":
    main()
