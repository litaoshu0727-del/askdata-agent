"""
从库文件和业务元数据生成出题人用的数据字典（建表语句 + 每张表、每个字段的说明）。

    python eval/blind_materials/make_dictionary.py sakila "DVD 租赁连锁店" runtime_data/sakila.db eval/blind_materials/sakila.md

格式照 chinook.md、ecommerce.md：说明只取元数据里的 description，不放别名和用途——出题人拿到的是
"刚接手这个库的人能看到的东西"，不是检索用的索引文本。tests/test_blind_materials.py 检查三份数据字典
和元数据的描述一致：第八套出题前发现过 ecommerce.md 落后于元数据四处。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

META = {
    "sakila": ("askdata_pipeline.sakila_data", "get_sakila_business_meta"),
    "chinook": ("askdata_pipeline.chinook_data", "get_chinook_business_meta"),
    "ecommerce": ("askdata_pipeline.ecommerce_data", "get_ecommerce_business_meta"),
}


def load_meta(dataset: str) -> dict:
    import importlib
    module, func = META[dataset]
    return getattr(importlib.import_module(module), func)()


def render(dataset: str, title: str, db_path: Path, meta: dict) -> str:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        lines = [f"# {dataset}（{title}） 数据库：Schema 与数据字典", "",
                 f"SQLite 库文件：`{db_path.name}`，共 {len(tables)} 张表。", "", "## 建表语句", "", "```sql"]
        for _, sql in tables:
            lines += [sql.strip() + ";", ""]
        lines[-1] = "```"
        lines += ["", "## 数据字典", ""]
        for name, _ in tables:
            table_meta = meta[name]
            lines += [f"### {name}", "", " ".join(table_meta["description"].split()), "",
                      "| 字段 | 类型 | 说明 |", "|---|---|---|"]
            for _, column, col_type, *_ in conn.execute(f'PRAGMA table_info("{name}")'):
                description = " ".join(table_meta["columns"][column]["description"].split())
                lines.append(f"| {column} | {col_type} | {description} |")
            lines.append("")
        return "\n".join(lines)
    finally:
        conn.close()


def main() -> None:
    dataset, title, db_path, out = sys.argv[1:5]
    Path(out).write_text(render(dataset, title, Path(db_path), load_meta(dataset)), encoding="utf-8")
    print(f"已写入 {out}")


if __name__ == "__main__":
    main()
