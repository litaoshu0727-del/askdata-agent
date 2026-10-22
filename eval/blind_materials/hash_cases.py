"""
逐题哈希，只输出题号：替换题目前存一份，替换后核对变了的是不是正好那几道。

    python eval/blind_materials/hash_cases.py snap <出题目录> <模块> <变量> <哈希文件>
    python eval/blind_materials/hash_cases.py diff <出题目录> <模块> <变量> <哈希文件> [应该变的题号,…]

哈希覆盖题目的全部字段和它在 alt_sql.json 里的候选路径。原先只放在临时目录里，第九套起收进仓库。
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import sys
from pathlib import Path


def snapshot(writer_dir: Path, module: str, var: str) -> dict:
    sys.path.insert(0, str(writer_dir))
    cases = getattr(importlib.import_module(module), var)
    alt_path = writer_dir / "alt_sql.json"
    alt = json.loads(alt_path.read_text(encoding="utf-8")) if alt_path.exists() else {}
    return {
        case.id: hashlib.sha256(json.dumps([dataclasses.asdict(case), alt.get(case.id)],
                                           ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        for case in cases
    }


def main() -> None:
    mode, writer_dir, module, var, path = sys.argv[1:6]
    now = snapshot(Path(writer_dir), module, var)
    if mode == "snap":
        Path(path).write_text(json.dumps(now, indent=0), encoding="utf-8")
        print(f"已存 {len(now)} 道题的哈希")
        return
    before = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = set(sys.argv[6].split(",")) if len(sys.argv) > 6 and sys.argv[6] else set()
    changed = {key for key in now if now[key] != before.get(key)}
    print("变了的题:", sorted(changed))
    print("应该变却没变:", sorted(expected - changed))
    print("不该变却变了:", sorted(changed - expected))
    print("题号集合是否一致:", set(now) == set(before))


if __name__ == "__main__":
    main()
