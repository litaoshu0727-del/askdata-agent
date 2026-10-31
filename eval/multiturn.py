"""
多轮追问评测：一组追问在一个新会话里按顺序问，每一轮单独判分。

    python -m eval.multiturn --dataset ecommerce --repeat 3 --save-runs runtime_data/runs/m1/e.jsonl
    python -m eval.multiturn --dataset chinook --case M1C03          # 只跑一组
    python -m eval.multiturn --dataset sakila --chunk 0/2            # 按组号隔一组取一组，拆给几个进程

走的是和 Web 工作台同一条路：DynamicAskDataService（意图路由 → 指代消解 → Text2SQL），记忆配置也一样。
会话记忆用这个进程自己的临时库，每组每次重复用新的 user_id、session_id，组和组之间、重复之间互不串。
长期记忆不开：它跨会话召回，会把同一组上一次重复的答案带进来。

判分沿用单轮评测器的 judge_case：每一轮比结果。追问被路由成"会话问答"（不查库）记为 routed_qa——这一套的追问
按出题规范都要查新数据，只靠前面的结果答不出来。陷阱轮被路由成会话问答、没给结果集，算通过。

某一轮崩了（超时、断网），整组换一个新会话从头重跑：只重跑那一轮的话，记忆里会多出一条没有回答的用户消息。

报告除了逐轮正确率，还给：追问在"同一次运行里前面各轮都答对"条件下的正确率（剥掉前面答错的连带影响）、
整组全对的比例、按追问形式的正确率、指代消解改写了几次、被路由成会话问答几次。
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
import uuid
from argparse import Namespace
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from askdata_memory import ConversationMemoryService, MemoryServiceConfig, ShortTermMemoryConfig  # noqa: E402
from askdata_pipeline.dynamic_service import DynamicAskDataService  # noqa: E402
from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from eval.cases import EvalCase, MultiTurnCase  # noqa: E402
from eval.runner import (  # noqa: E402
    DATASETS,
    CaseOutcome,
    RunRecorder,
    build_pipeline,
    classify_error,
    git_revision,
    judge_case,
    load_expected,
    pad,
    select_chunk,
)

FOLLOW_UP_PREFIX = "追问:"


def load_banks() -> Dict[str, Dict[str, List[MultiTurnCase]]]:
    """多轮题库按库名分。题库模块在冻结时加进来，还没有时返回空。"""
    banks: Dict[str, Dict[str, List[MultiTurnCase]]] = {}
    try:
        from eval.cases_multiturn1 import MULTITURN1_BANKS
    except ImportError:
        pass
    else:
        banks["multiturn1"] = MULTITURN1_BANKS
    return banks


@dataclass
class TurnRun:
    """一组追问里一轮的一次运行。"""

    outcome: CaseOutcome
    route: str = ""
    rewritten: str = ""


@dataclass
class ChainRun:
    """一组追问的一次运行：各轮按顺序。崩在中途时，后面的轮没有跑。"""

    chain: MultiTurnCase
    repeat: int
    turns: List[TurnRun] = field(default_factory=list)
    attempts: int = 1

    @property
    def completed(self) -> bool:
        return len(self.turns) == len(self.chain.turns) and all(t.outcome.status != "crash" for t in self.turns)


def build_service(args: Namespace, database_name: str, db_path: Path, memory_db: Path) -> DynamicAskDataService:
    """和 Web 工作台同样的组装：同一条流水线、同样的短期记忆窗口。"""
    pipeline = build_pipeline(args, database_name, db_path, "full")
    memory = ConversationMemoryService(
        MemoryServiceConfig(
            db_path=memory_db,
            short_term=ShortTermMemoryConfig(max_window_messages=8, max_window_tokens=4000, async_summary=True),
        )
    )
    return DynamicAskDataService(pipeline=pipeline, memory=memory)


def run_turn(service: Any, user_id: str, session_id: str, turn: EvalCase, expected: List[Dict[str, Any]]) -> TurnRun:
    started = time.time()
    try:
        routed = service.run(user_id=user_id, session_id=session_id, query=turn.query, enable_long_term=False)
    except Exception as exc:
        return TurnRun(CaseOutcome(case=turn, status="crash", detail=f"{type(exc).__name__}: {exc}", elapsed=time.time() - started))

    elapsed = time.time() - started
    route = routed.decision.route.value
    result = routed.pipeline_result
    if result is None:
        if turn.expect_unanswerable:
            outcome = CaseOutcome(case=turn, status="pass", detail="路由成会话问答，没有给出结果集", elapsed=elapsed)
        else:
            outcome = CaseOutcome(case=turn, status="routed_qa", detail="没查库：按会话问答回答了", elapsed=elapsed)
        outcome.trace = {"answer": routed.answer[:500]}
        return TurnRun(outcome, route=route)

    return TurnRun(judge_case(turn, result, expected, elapsed), route=route, rewritten=result.rewritten_query)


def run_chain(service: Any, chain: MultiTurnCase, expected: Dict[str, List[Dict[str, Any]]], repeat: int, retries: int) -> ChainRun:
    """跑一组。某一轮崩了且是瞬时故障，整组换新会话重跑。"""
    for attempt in range(1, retries + 2):
        run = ChainRun(chain=chain, repeat=repeat, attempts=attempt)
        user_id, session_id = f"eval-{uuid.uuid4().hex[:8]}", f"eval-{uuid.uuid4().hex[:12]}"
        for turn in chain.turns:
            turn_run = run_turn(service, user_id, session_id, turn, expected[turn.id])
            run.turns.append(turn_run)
            if turn_run.outcome.status == "crash":
                break
        if run.completed:
            return run
        detail = run.turns[-1].outcome.detail
        if classify_error(detail) == "persistent" or attempt > retries:
            return run
        print(f"{'':<8}↻ {run.turns[-1].outcome.case.id} 瞬时故障，整组重跑 {attempt}/{retries}：{detail[:60]}", flush=True)
    return run


def follow_up_tags(turn: EvalCase) -> List[str]:
    return [tag for tag in turn.tags if tag.startswith(FOLLOW_UP_PREFIX)]


def summarize(runs: Sequence[ChainRun]) -> Dict[str, Any]:
    """逐轮、按条件、按追问形式汇总。陷阱轮单独算，不混进追问正确率。"""
    first, follow, conditional, traps = Counter(), Counter(), Counter(), Counter()
    by_tag: Dict[str, Counter] = defaultdict(Counter)
    statuses, routes = Counter(), Counter()
    chains_ok = chains_total = rewrites = 0

    for run in runs:
        if not run.completed:
            continue
        chains_total += 1
        chains_ok += all(t.outcome.passed for t in run.turns)
        previous_ok = True
        for index, turn_run in enumerate(run.turns):
            turn, passed = turn_run.outcome.case, turn_run.outcome.passed
            statuses[turn_run.outcome.status] += 1
            if turn.expect_unanswerable:
                traps[passed] += 1
            elif index == 0:
                first[passed] += 1
            else:
                follow[passed] += 1
                routes[turn_run.route] += 1
                rewrites += bool(turn_run.rewritten)
                if previous_ok:
                    conditional[passed] += 1
                for tag in follow_up_tags(turn):
                    by_tag[tag][passed] += 1
            previous_ok = previous_ok and passed

    return {
        "first": first, "follow": follow, "conditional": conditional, "traps": traps, "by_tag": by_tag,
        "statuses": statuses, "routes": routes, "rewrites": rewrites,
        "chains_ok": chains_ok, "chains_total": chains_total,
        "incomplete": sum(not run.completed for run in runs),
    }


def rate(counter: Counter) -> str:
    total = counter[True] + counter[False]
    return f"{counter[True]}/{total}（{counter[True] / total:.0%}）" if total else "—"


def report(chains: Sequence[MultiTurnCase], runs: Sequence[ChainRun]) -> None:
    print("\n" + "=" * 92)
    print("逐组（每一轮：对的次数/跑完的次数）")
    by_chain: Dict[str, List[ChainRun]] = defaultdict(list)
    for run in runs:
        by_chain[run.chain.id].append(run)
    for chain in chains:
        cells = []
        for index, turn in enumerate(chain.turns):
            done = [r.turns[index] for r in by_chain[chain.id] if len(r.turns) > index]
            mark = "⊘" if turn.expect_unanswerable else ""
            cells.append(f"{mark}{sum(t.outcome.passed for t in done)}/{len(done)}")
        print(f"  {pad(chain.id, 8)} " + "  ".join(pad(cell, 6) for cell in cells))

    s = summarize(runs)
    print("\n汇总（按运行）")
    print(f"  第 1 轮                  {rate(s['first'])}")
    print(f"  追问                     {rate(s['follow'])}")
    print(f"  追问，前面各轮都答对时   {rate(s['conditional'])}")
    print(f"  陷阱轮没有编             {rate(s['traps'])}")
    print(f"  整组全对                 {s['chains_ok']}/{s['chains_total']}")
    print(f"  追问里：指代消解改写了 {s['rewrites']} 次；路由 " + "、".join(f"{k} {v}" for k, v in s["routes"].most_common()))
    failures = {k: v for k, v in s["statuses"].items() if k != "pass"}
    if failures:
        print("  失败类型：" + "、".join(f"{k} {v}" for k, v in sorted(failures.items(), key=lambda kv: -kv[1])))
    if s["incomplete"]:
        print(f"  ⚠️ {s['incomplete']} 次运行中途崩了，没有算进上面的数字")
    if s["by_tag"]:
        print("\n按追问形式")
        for tag, counter in sorted(s["by_tag"].items(), key=lambda kv: kv[0]):
            print(f"  {pad(tag, 16)} {rate(counter)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多轮追问评测")
    parser.add_argument("--dataset", default="ecommerce", choices=["ecommerce", "chinook", "sakila"])
    parser.add_argument("--bank", default="multiturn1")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--case", default="", help="只跑指定组号，例如 M1E03")
    parser.add_argument("--chunk", default="", help="i/n：按组号隔 n 组取一组，取第 i 份")
    parser.add_argument("--retries", type=int, default=2, help="某一轮瞬时故障时整组重跑的次数")
    parser.add_argument("--db-path", default="", help="电商库每建一次流水线都会删掉重建，拆进程跑时每个进程给一份自己的")
    parser.add_argument("--save-runs", default="", help="每一轮一行 JSON，追加写入这个文件")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    logging.getLogger("askdata").disabled = True

    banks = load_banks()
    if args.bank not in banks:
        raise SystemExit(f"没有 {args.bank} 题库。现有：{'、'.join(banks) or '无'}")
    chains = list(banks[args.bank].get(args.dataset) or [])
    if args.case:
        chains = [c for c in chains if c.id.upper() == args.case.upper()]
    if args.chunk:
        chains = select_chunk(chains, args.chunk)
    if not chains:
        raise SystemExit("没有匹配的题组")

    _, database_name, default_db = DATASETS[args.dataset]
    db_path = Path(args.db_path) if args.db_path else default_db
    pipeline_args = Namespace(dataset=args.dataset, self_consistency=1,
                              repair=PipelineConfig.sql_repair_attempts, sql_rules="on")

    turns = sum(len(c.turns) for c in chains)
    repeat = max(1, args.repeat)
    print("=" * 92)
    print(f"AskData 多轮评测　·　{args.dataset}　·　{args.bank}　·　{len(chains)} 组 {turns} 轮　·　每组 {repeat} 次")
    print("=" * 92)

    recorder = None
    if args.save_runs:
        recorder = RunRecorder(Path(args.save_runs), {
            "run_id": time.strftime("%Y%m%d-%H%M%S"), "commit": git_revision(),
            "dataset": args.dataset, "bank": args.bank,
        })
        print(f"过程记录：{args.save_runs}（提交 {recorder.meta['commit']}）")

    runs: List[ChainRun] = []
    with tempfile.TemporaryDirectory() as tmp:
        service = build_service(pipeline_args, database_name, db_path, Path(tmp) / "memory.db")
        # 流水线建好之后再取参考答案：电商库在建流水线时重建
        expected = {turn.id: load_expected(db_path, turn) for chain in chains for turn in chain.turns}
        try:
            for index, chain in enumerate(chains, start=1):
                print(f"  [{index}/{len(chains)}] {chain.id}", flush=True)
                for r in range(1, repeat + 1):
                    run = run_chain(service, chain, expected, r, args.retries)
                    runs.append(run)
                    marks = "".join("✓" if t.outcome.passed else "✗" for t in run.turns)
                    print(f"{'':<8}第 {r} 次 {marks}" + ("（中途崩了）" if not run.completed else ""), flush=True)
                    if recorder:
                        for position, turn_run in enumerate(run.turns, start=1):
                            recorder.write(turn_run.outcome, "full", r, extra={
                                "chain_id": chain.id, "turn": position, "route": turn_run.route,
                                "chain_attempts": run.attempts,
                            })
                    last = run.turns[-1].outcome
                    if not run.completed and classify_error(last.detail) == "persistent":
                        raise SystemExit(f"持续性故障，评测中止：{last.detail[:120]}")
        finally:
            if recorder:
                recorder.close()
            # 等后台的摘要任务做完再删临时目录，不然它回头打开记忆库时库已经没了
            service.memory.close()

    report(chains, runs)


if __name__ == "__main__":
    main()
