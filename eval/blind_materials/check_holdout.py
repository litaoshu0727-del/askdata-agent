"""
盲写题冻结前的机械校验和去重。只输出题号和检查项——不打印题目内容（问题、SQL、字段、结果），
SQL 报错只打印异常类型：跑校验的人在冻结前不该看到题。

    python eval/blind_materials/check_holdout.py <出题目录> --module cases_holdout9 --var HOLDOUT9_SAKILA_CASES \\
        --dataset sakila --prefix H9S --count 40 --traps 4 --min-hard 14 --max-easy 4 --min-tables 13

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
- 去重：和全部已有题库（含探针）以及这一套自己的其他题比，问法相似度 >= 0.6 或参考答案结果集相同
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
    args = parser.parse_args()

    writer_dir = Path(args.writer_dir)
    sys.path.insert(0, str(writer_dir))
    cases = getattr(importlib.import_module(args.module), args.var)
    alt_path = writer_dir / "alt_sql.json"
    alt = json.loads(alt_path.read_text(encoding="utf-8")) if alt_path.exists() else {}
    db_path = ROOT / DATASETS[args.dataset][2]
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    columns_by_table = {t: [row[1] for row in conn.execute(f'PRAGMA table_info("{t}")')] for t in tables}

    # ---- 题号
    ids = [c.id for c in cases]
    if len(cases) != args.count:
        fail(args.dataset, f"题数 {len(cases)}，应为 {args.count}")
    if len(set(ids)) != len(ids):
        fail(args.dataset, "题号重复")
    for c in cases:
        if not re.fullmatch(rf"{args.prefix}\d\d", c.id):
            fail(c.id, "题号格式不对")
    existing = {case.id for bank, banks in BANKS.items() if bank != args.self_bank for pool in banks.values() for case in pool} | \
               {case.id for pool, _, _ in DATASETS.values() for case in pool}
    for c in cases:
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
    for a, b in itertools.combinations(cases, 2):
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
