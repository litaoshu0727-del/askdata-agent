"""
探针一键回归：跑全部（或指定批次的）探针，按批次汇总，和上一次比。

    python -m eval.probe_regression                              # 全部探针，每题 3 次，6 个进程并行，和上一次完整运行比
    python -m eval.probe_regression --batches 探针:全称,探针:口径   # 只跑这几批
    python -m eval.probe_regression --report runtime_data/probe_runs/<目录>       # 不跑，只汇总已有的一次运行
    python -m eval.probe_regression --baseline runtime_data/probe_runs/<目录>     # 指定和哪一次比

探针原先只在改规则时手动跑其中一批，新规则会不会把旧问题带回来，没人看。这个脚本回答的就是这一个问题：
改了提示词、元数据之后，修过的那些失败有没有回来。探针是对着具体的失败写的，分数不是泛化能力的证据。

每次运行一个目录 runtime_data/probe_runs/<时间>_<提交>/：各批次的 JSONL（评测器 --save-runs 的格式）、
日志、summary.json。和上一次比用的是 summary.json，按题比通过率；题面或参考答案改过的题（指纹不同）不比。

要调真实模型，CI 里跑不了；tests/test_probe_regression.py 只测规划、汇总和比较。

实现上每个批次起一个评测器进程（python -m eval.runner --bank probes --tag 批次），判分、重试、熔断都沿用评测器。
电商库每次建流水线都会删掉重建（create_ecommerce_demo_database），几个进程共用一个库文件会互相删，
所以每个电商进程用运行目录里自己的一份；Chinook 直接读 runtime_data/chinook.db，不复制。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.cases import EvalCase  # noqa: E402
from eval.cases_probes import PROBE_BANKS  # noqa: E402

RUNS_DIR = ROOT / "runtime_data" / "probe_runs"
BATCH_PREFIX = "探针:"
SHARP_DROP = 0.5  # 通过率掉一半以上（3 次里从 3 掉到 1）算明显变差


@dataclass(frozen=True)
class Job:
    dataset: str
    batch: str
    case_ids: tuple

    @property
    def name(self) -> str:
        return f"{self.dataset}__{self.batch.replace(':', '_')}"


def batch_of(case: EvalCase) -> str:
    """探针所属的批次（tags 里唯一一个"探针:"开头的）。tests/test_probes.py 保证恰好一个。"""
    return next(tag for tag in case.tags if tag.startswith(BATCH_PREFIX))


def role_of(case: EvalCase) -> str:
    """对照题本来就该那样写；其余都是对着一类失败写的。"""
    return "对照" if "对照" in case.tags else "该出错"


def fingerprint(case: EvalCase) -> str:
    """题面和参考答案的指纹。改过参考答案的题（比如口径定下来那次）和改之前的分数不能比。"""
    text = json.dumps([case.query, case.reference_sql, case.expect_unanswerable, case.ordered], ensure_ascii=False)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def case_index(banks: Dict[str, Sequence[EvalCase]] = PROBE_BANKS) -> Dict[str, dict]:
    """dataset/题号 → 批次、角色、指纹。"""
    return {
        f"{dataset}/{case.id}": {
            "dataset": dataset, "id": case.id, "batch": batch_of(case),
            "role": role_of(case), "fingerprint": fingerprint(case),
        }
        for dataset, cases in banks.items() for case in cases
    }


def plan_jobs(banks: Dict[str, Sequence[EvalCase]] = PROBE_BANKS, batches: Optional[Sequence[str]] = None) -> List[Job]:
    """每个（库, 批次）一个进程，题多的排在前面先跑，免得最后剩一个大批次拖着。"""
    known = {batch_of(case) for cases in banks.values() for case in cases}
    if batches:
        unknown = set(batches) - known
        if unknown:
            raise SystemExit(f"没有这些批次：{'、'.join(sorted(unknown))}。现有：{'、'.join(sorted(known))}")
    groups: Dict[tuple, List[str]] = {}
    for dataset, cases in banks.items():
        for case in cases:
            batch = batch_of(case)
            if batches and batch not in batches:
                continue
            groups.setdefault((dataset, batch), []).append(case.id)
    jobs = [Job(dataset, batch, tuple(ids)) for (dataset, batch), ids in groups.items()]
    return sorted(jobs, key=lambda job: (-len(job.case_ids), job.dataset, job.batch))


def run_jobs(jobs: Sequence[Job], run_dir: Path, repeat: int, parallel: int) -> Dict[str, int]:
    """起评测器进程跑各批次，最多 parallel 个同时跑。返回各批次的退出码（2 = 评测器熔断中止）。"""
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "db").mkdir(parents=True, exist_ok=True)
    pending, running, codes = list(jobs), {}, {}
    started = time.time()
    while pending or running:
        while pending and len(running) < parallel:
            job = pending.pop(0)
            cmd = [sys.executable, "-m", "eval.runner", "--dataset", job.dataset, "--bank", "probes",
                   "--tag", job.batch, "--repeat", str(repeat), "--save-runs", str(run_dir / f"{job.name}.jsonl")]
            if job.dataset != "chinook":
                cmd += ["--db-path", str(run_dir / "db" / f"{job.name}.db")]
            log = (run_dir / "logs" / f"{job.name}.log").open("w", encoding="utf-8")
            running[job] = (subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT), log, time.time())
        time.sleep(2)
        for job, (proc, log, since) in list(running.items()):
            if proc.poll() is None:
                continue
            log.close()
            codes[job.name] = proc.returncode
            del running[job]
            mark = "" if proc.returncode == 0 else f"  【退出码 {proc.returncode}，见 logs/{job.name}.log】"
            print(f"  完成 {job.dataset:9} {job.batch:12} {len(job.case_ids):>3} 题 × {repeat}"
                  f"　{time.time() - since:5.0f}s　（已用 {time.time() - started:.0f}s，"
                  f"剩 {len(pending) + len(running)} 批）{mark}", flush=True)
    for db in (run_dir / "db").glob("*.db"):
        db.unlink()
    return codes


def summarize(run_dir: Path, index: Dict[str, dict], jobs: Sequence[Job], repeat: int, meta: dict) -> dict:
    """读各批次的 JSONL，按题数通过次数。少了记录（中途熔断、进程崩了）的题记为不完整。"""
    statuses: Dict[str, List[str]] = {}
    for path in sorted(run_dir.glob("*.jsonl")):
        for line in path.open(encoding="utf-8"):
            record = json.loads(line)
            statuses.setdefault(f"{record['dataset']}/{record['case_id']}", []).append(record["status"])
    cases = {}
    for job in jobs:
        for case_id in job.case_ids:
            key = f"{job.dataset}/{case_id}"
            got = statuses.get(key, [])
            cases[key] = {**index[key], "passes": sum(s == "pass" for s in got), "runs": len(got), "statuses": got}
    incomplete = sorted(key for key, item in cases.items() if item["runs"] < repeat)
    crashes = sum(s == "crash" for item in cases.values() for s in item["statuses"])
    return {"meta": {**meta, "repeat": repeat, "complete": not incomplete, "incomplete": incomplete, "crashes": crashes},
            "cases": cases}


def rate(item: dict) -> Optional[float]:
    return item["passes"] / item["runs"] if item["runs"] else None


def compare(current: dict, baseline: Optional[dict]) -> dict:
    """按题比通过率。指纹不同的不比；只在一边有的列出来。"""
    result = {"better": [], "worse": [], "sharp": [], "changed": [], "new": [], "gone": []}
    if not baseline:
        return result
    base_cases = baseline["cases"]
    for key, item in current["cases"].items():
        old = base_cases.get(key)
        if old is None:
            result["new"].append(key)
            continue
        if old["fingerprint"] != item["fingerprint"]:
            result["changed"].append(key)
            continue
        before, after = rate(old), rate(item)
        if before is None or after is None or before == after:
            continue
        entry = (key, f"{old['passes']}/{old['runs']}", f"{item['passes']}/{item['runs']}")
        if after > before:
            result["better"].append(entry)
        else:
            result["worse"].append(entry)
            if before - after >= SHARP_DROP:
                result["sharp"].append(entry)
    result["gone"] = sorted(set(base_cases) - set(current["cases"]))
    return result


def sign_test(better: int, worse: int) -> float:
    """双侧符号检验。"""
    n = better + worse
    if not n:
        return 1.0
    k = min(better, worse)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def pad(text: str, width: int) -> str:
    import unicodedata
    shown = sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)
    return text + " " * max(0, width - shown)


def render(current: dict, baseline: Optional[dict], diff: dict) -> str:
    meta = current["meta"]
    lines = ["=" * 96,
             f"探针回归　提交 {meta['commit']}　每题 {meta['repeat']} 次　{len(current['cases'])} 题",
             "=" * 96]
    if meta.get("changed_files"):
        lines.append(f"工作区改动（{len(meta['changed_files'])} 个文件）：{'、'.join(meta['changed_files'][:8])}"
                     + ("……" if len(meta["changed_files"]) > 8 else ""))
    if baseline:
        lines.append(f"对比：{baseline['meta'].get('run_dir', '?')}（提交 {baseline['meta']['commit']}，"
                     f"每题 {baseline['meta']['repeat']} 次）")
    else:
        lines.append("对比：没有可比的上一次完整运行")
    lines.append("")

    header = pad("批次", 20) + pad("库", 11) + pad("该出错", 12) + pad("对照", 10) + pad("本次", 8) + pad("上次", 8) + "变好 / 变差"
    lines += [header, "-" * 96]
    groups: Dict[tuple, List[str]] = {}
    for key, item in current["cases"].items():
        groups.setdefault((item["batch"], item["dataset"]), []).append(key)
    better_keys = {entry[0] for entry in diff["better"]}
    worse_keys = {entry[0] for entry in diff["worse"]}
    total = [0, 0]
    for (batch, dataset), keys in sorted(groups.items()):
        cells = {}
        for role in ("该出错", "对照"):
            items = [current["cases"][k] for k in keys if current["cases"][k]["role"] == role]
            cells[role] = f"{sum(i['passes'] for i in items)}/{sum(i['runs'] for i in items)}" if items else "—"
        passes = sum(current["cases"][k]["passes"] for k in keys)
        runs = sum(current["cases"][k]["runs"] for k in keys)
        total[0] += passes
        total[1] += runs
        now = f"{passes / runs:.0%}" if runs else "—"
        before = "—"
        if baseline:
            olds = [baseline["cases"][k] for k in keys
                    if k in baseline["cases"] and baseline["cases"][k]["fingerprint"] == current["cases"][k]["fingerprint"]]
            old_runs = sum(o["runs"] for o in olds)
            before = f"{sum(o['passes'] for o in olds) / old_runs:.0%}" if old_runs else "—"
        moves = f"{sum(k in better_keys for k in keys)} / {sum(k in worse_keys for k in keys)}" if baseline else ""
        lines.append(pad(batch, 20) + pad(dataset, 11) + pad(cells["该出错"], 12) + pad(cells["对照"], 10)
                     + pad(now, 8) + pad(before, 8) + moves)
    lines += ["-" * 96, f"合计 {total[0]}/{total[1]}" + (f"　{total[0] / total[1]:.1%}" if total[1] else "")]

    if baseline:
        lines.append(f"逐题：变好 {len(diff['better'])}、变差 {len(diff['worse'])}，"
                     f"符号检验 p≈{sign_test(len(diff['better']), len(diff['worse'])):.2f}")
        if diff["sharp"]:
            lines.append("明显变差（通过率掉一半以上）：" + "、".join(f"{k} {a}→{b}" for k, a, b in diff["sharp"]))
        rest = [entry for entry in diff["worse"] if entry not in diff["sharp"]]
        if rest:
            lines.append("变差：" + "、".join(f"{k} {a}→{b}" for k, a, b in rest))
        if diff["better"]:
            lines.append("变好：" + "、".join(f"{k} {a}→{b}" for k, a, b in diff["better"]))
        if diff["changed"]:
            lines.append("题目改过、不比：" + "、".join(diff["changed"]))
        if diff["new"]:
            lines.append(f"上次没有的题：{len(diff['new'])} 道")

    failing = [(k, i) for k, i in current["cases"].items() if i["passes"] < i["runs"]]
    if failing:
        lines.append("")
        lines.append("本次没有全对的题：")
        for key, item in sorted(failing):
            lines.append(f"  {key:16} {item['passes']}/{item['runs']}　{item['batch']}"
                         f"{'（对照）' if item['role'] == '对照' else ''}　{' '.join(item['statuses'])}")
    if not meta["complete"]:
        lines.append("")
        lines.append(f"⚠️ 不完整：{len(meta['incomplete'])} 道题的记录不够 {meta['repeat']} 次（熔断或进程崩了），"
                     f"它们的分数不可信：{'、'.join(meta['incomplete'][:10])}")
    return "\n".join(lines)


def latest_baseline(runs_dir: Path, current_dir: Path, keys: Sequence[str]) -> Optional[Path]:
    """
    在这次之前、最近一次完整且覆盖了这次全部题目的运行。

    目录名以时间开头，按名字排序就是按时间。只跑了一两批的运行不会被当成全量运行的对比对象。
    """
    for path in sorted(runs_dir.glob("*/summary.json"), reverse=True):
        if path.parent.name >= current_dir.name:
            continue
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary["meta"].get("complete") and set(keys) <= set(summary["cases"]):
            return path.parent
    return None


def changed_files() -> List[str]:
    """工作区里改过、还没提交的文件。探针常在规则没提交时跑，光看提交号分不出版本。"""
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line[3:] for line in out.splitlines() if line.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="探针一键回归")
    parser.add_argument("--batches", default="", help="只跑这几批，逗号分隔，例如 探针:全称,探针:口径")
    parser.add_argument("--repeat", type=int, default=3, help="每题跑几次")
    parser.add_argument("--parallel", type=int, default=6, help="最多几个评测器进程同时跑")
    parser.add_argument("--baseline", default="latest", help="和哪一次比：latest（默认）、none，或一个运行目录")
    parser.add_argument("--report", default="", help="不跑，只汇总这个已有的运行目录")
    parser.add_argument("--strict", action="store_true", help="有题明显变差时退出码为 1")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    batches = [b.strip() for b in args.batches.split(",") if b.strip()] or None
    index = case_index()

    if args.report:
        run_dir = Path(args.report)
        current = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    else:
        from eval.runner import git_revision
        jobs = plan_jobs(batches=batches)
        commit = git_revision()
        run_dir = RUNS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}_{commit}"
        meta = {"commit": commit, "changed_files": changed_files(), "batches": batches or "全部",
                "started": time.strftime("%Y-%m-%d %H:%M:%S"), "run_dir": str(run_dir.relative_to(ROOT))}
        total = sum(len(job.case_ids) for job in jobs)
        print(f"探针回归：{len(jobs)} 批、{total} 题，每题 {args.repeat} 次，{args.parallel} 个进程并行 → {meta['run_dir']}",
              flush=True)
        codes = run_jobs(jobs, run_dir, args.repeat, args.parallel)
        meta.update(finished=time.strftime("%Y-%m-%d %H:%M:%S"), exit_codes=codes)
        current = summarize(run_dir, index, jobs, args.repeat, meta)
        (run_dir / "summary.json").write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")

    baseline = None
    if args.baseline != "none":
        base_dir = (latest_baseline(RUNS_DIR, run_dir, list(current["cases"])) if args.baseline == "latest"
                    else Path(args.baseline))
        if base_dir:
            baseline = json.loads((base_dir / "summary.json").read_text(encoding="utf-8"))
    diff = compare(current, baseline)
    report = render(current, baseline, diff)
    print("\n" + report)
    if not args.report:
        (run_dir / "report.txt").write_text(report + "\n", encoding="utf-8")

    if not current["meta"]["complete"]:
        sys.exit(2)
    if args.strict and diff["sharp"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
