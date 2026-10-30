"""
用现在的判分重判存下的运行记录，不调模型。

    python -m eval.rejudge_runs                                   # runtime_data/runs 和 runtime_data/probe_runs 下全部
    python -m eval.rejudge_runs runtime_data/runs/h10 runtime_data/runs/h9

判分改了以后，要知道以前的分数里有多少是按旧比法才算对的。记录里存了最后一步的 SQL，
在同一个库上重新执行，旧比法、新比法各判一次。

只重判当时是"对"或"结果不符"的记录：SQL 报错、没生成 SQL、陷阱题，比法改了也不受影响。
旧比法的结论先和记录里的状态核对一遍，对不上的（参考答案后来改过、库重建过）单独列出，不算进翻转。
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.runner import (  # noqa: E402
    BANK_DATASET,
    BANKS,
    DATASETS,
    MAX_EXTRA_COLUMN_COMBINATIONS,
    case_ndigits,
    extra_columns_match,
    load_expected,
    normalize_value,
    rows_match,
)
from mcp_router.sqlite_executor import unique_column_names  # noqa: E402

DEFAULT_PATHS = [ROOT / "runtime_data" / "runs", ROOT / "runtime_data" / "probe_runs"]
MAX_ROWS = 10000        # 和执行器的默认上限一致
MAX_SECONDS = 30.0


def legacy_match(actual: Sequence[Dict[str, Any]], expected: Sequence[Dict[str, Any]], ordered: bool, ndigits: int) -> bool:
    """改之前的比法：每行的值各自排序再比；多出的列按同样的比法挑。"""
    def normalize(rows):
        normalized = [tuple(sorted(normalize_value(v, ndigits) for v in row.values())) for row in rows]
        return normalized if ordered else sorted(normalized)

    target = normalize(expected)
    if normalize(actual) == target:
        return True

    if not actual or len(actual) != len(expected):
        return False
    columns = list(actual[0])
    width = len(expected[0]) if expected else 0
    if len(columns) <= width or width == 0 or math.comb(len(columns), width) > MAX_EXTRA_COLUMN_COMBINATIONS:
        return False
    return any(
        normalize([{name: row.get(name) for name in chosen} for row in actual]) == target
        for chosen in itertools.combinations(columns, width)
    )


def current_match(actual, expected, ordered: bool, ndigits: int) -> bool:
    return rows_match(actual, expected, ordered, ndigits) or extra_columns_match(actual, expected, ordered, ndigits) > 0


def execute(db_path: Path, sql: str) -> List[Dict[str, Any]]:
    """和执行器一样取结果：只读、按位置填列名、超过上限截断。"""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        deadline = time.monotonic() + MAX_SECONDS
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        cursor = conn.execute(sql)
        columns = unique_column_names([item[0] for item in (cursor.description or [])])
        return [dict(zip(columns, row)) for row in cursor.fetchmany(MAX_ROWS)]
    finally:
        conn.close()


def iter_records(paths: Sequence[Path]):
    for path in paths:
        files = [path] if path.is_file() else sorted(path.rglob("*.jsonl"))
        for file in files:
            with file.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        yield file, json.loads(line)


def find_case(dataset: str, bank: str, case_id: str):
    """
    按题库找题。探针实验的记录用的是临时题库名（probe-main、probe-b1、probe-holdout6……），
    找不到就按题号在所有题库里找——题号跨题库不重复（tests/test_probes.py 守着）。
    题后来改过的，旧比法复现不了当时的结论，会被单独列出，不会混进翻转。
    """
    case_dataset = BANK_DATASET.get(dataset, dataset)
    pools = [DATASETS[case_dataset][0]] if bank == "main" else [(BANKS.get(bank) or {}).get(case_dataset) or []]
    pools += [DATASETS[case_dataset][0]] + [(banks.get(case_dataset) or []) for banks in BANKS.values()]
    return next((case for cases in pools for case in cases if case.id == case_id), None)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="用现在的判分重判存下的运行记录（不调模型）")
    parser.add_argument("paths", nargs="*", type=Path, help="JSONL 文件或目录，默认 runtime_data/runs 和 runtime_data/probe_runs")
    parser.add_argument("--json", type=Path, default=None, help="把翻转的明细写到这个文件")
    args = parser.parse_args(argv)
    paths = args.paths or [path for path in DEFAULT_PATHS if path.exists()]

    expected_cache: Dict[Tuple[str, str, str], Any] = {}
    verdict_cache: Dict[Tuple[str, str, str, str], Tuple[bool, bool]] = {}
    counts: Counter = Counter()
    flips: Dict[Tuple[str, str, str], Dict[str, Any]] = defaultdict(lambda: {"records": 0, "sql": set(), "files": set()})
    stale: Counter = Counter()

    for file, record in iter_records(paths):
        if record.get("status") not in {"pass", "wrong_result"} or not record.get("generated_sql"):
            continue
        dataset, bank, case_id = record.get("dataset", ""), record.get("bank", "main"), record.get("case_id", "")
        case = find_case(dataset, bank, case_id) if dataset in DATASETS else None
        if case is None or case.expect_unanswerable:
            counts["题已不在题库"] += 1
            continue

        db_path = ROOT / DATASETS[dataset][2]
        key = (dataset, bank, case_id)
        if key not in expected_cache:
            try:
                expected_cache[key] = load_expected(db_path, case)
            except sqlite3.Error:
                expected_cache[key] = None
        expected = expected_cache[key]
        if expected is None:
            counts["参考 SQL 跑不通"] += 1
            continue

        sql = record["generated_sql"]
        if key + (sql,) not in verdict_cache:
            try:
                actual = execute(db_path, sql)
            except sqlite3.Error:
                verdict_cache[key + (sql,)] = None
            else:
                ndigits = case_ndigits(case)
                verdict_cache[key + (sql,)] = (
                    legacy_match(actual, expected, case.ordered, ndigits),
                    current_match(actual, expected, case.ordered, ndigits),
                )
        verdict = verdict_cache[key + (sql,)]
        if verdict is None:
            counts["重新执行报错"] += 1
            continue

        legacy, current = verdict
        counts["重判"] += 1
        if legacy != (record["status"] == "pass"):
            # 旧比法都复现不了当时的结论：参考答案或库后来改过，这条不拿来说明比法的差别
            counts["旧比法和记录不一致"] += 1
            stale[f"{bank}:{case_id}"] += 1
            continue
        counts["当时判对" if legacy else "当时判错"] += 1
        if legacy and not current:
            counts["对→错"] += 1
            item = flips[key]
            item["records"] += 1
            item["sql"].add(sql)
            item["files"].add(str(file.relative_to(ROOT)) if file.is_relative_to(ROOT) else str(file))
        elif current and not legacy:
            counts["错→对"] += 1

    print(f"重判 {counts['重判']} 条（不同的题 × SQL {sum(v is not None for v in verdict_cache.values())} 种）")
    print(f"  旧比法复现了当时结论 {counts['当时判对'] + counts['当时判错']} 条：当时判对 {counts['当时判对']}、判错 {counts['当时判错']}")
    print(f"  新比法下 对→错 {counts['对→错']} 条，错→对 {counts['错→对']} 条")
    skipped = {name: counts[name] for name in ("旧比法和记录不一致", "题已不在题库", "参考 SQL 跑不通", "重新执行报错") if counts[name]}
    if skipped:
        print("  没算进比较：" + "，".join(f"{name} {value}" for name, value in skipped.items()))
    if stale:
        print("  旧比法和记录不一致的题：" + "、".join(f"{name}×{count}" for name, count in stale.most_common()))

    if flips:
        print("\n按新比法翻成错的题：")
        for (dataset, bank, case_id), item in sorted(flips.items()):
            print(f"  {dataset:13} {bank}:{case_id}  {item['records']} 条记录，{len(item['sql'])} 种 SQL")
            for sql in sorted(item["sql"]):
                print(f"      {sql[:160]}")

    if args.json:
        args.json.write_text(json.dumps([
            {"dataset": d, "bank": b, "case_id": c, "records": item["records"], "sql": sorted(item["sql"]), "files": sorted(item["files"])}
            for (d, b, c), item in sorted(flips.items())
        ], ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
