from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import re  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval" / "blind_materials"))

from make_dictionary import META, load_meta  # noqa: E402

MATERIALS = ROOT / "eval" / "blind_materials"


def squash(text: str) -> str:
    return " ".join(text.split())


class DictionaryMatchesMetaTest(unittest.TestCase):
    """
    出题人拿到的数据字典和系统看到的元数据要一致。

    第八套出题前发现 ecommerce.md 还是第七套时的版本：订单结构、口径约定、order_status、pay_time
    四处描述没跟上元数据。出题人照着旧说明写题，系统照着新元数据答，判分就不公平。
    """

    def test_every_table_and_column_description_appears(self):
        for dataset in META:
            path = MATERIALS / f"{dataset}.md"
            meta = load_meta(dataset)
            text = path.read_text(encoding="utf-8")
            sections = {match.group(1): match.group(2)
                        for match in re.finditer(r"^### (\w+)\n(.*?)(?=^### |\Z)", text, re.S | re.M)}
            for table, table_meta in meta.items():
                with self.subTest(库=dataset, 表=table):
                    self.assertIn(table, sections)
                    section = squash(sections[table])
                    self.assertIn(squash(table_meta["description"]), section)
                    for column, column_meta in table_meta["columns"].items():
                        self.assertIn(squash(column_meta["description"]), section, f"{table}.{column}")


if __name__ == "__main__":
    unittest.main()
