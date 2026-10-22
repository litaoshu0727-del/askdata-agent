from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.cases import EvalCase  # noqa: E402
from eval.runner import select_chunk  # noqa: E402


class ChunkTest(unittest.TestCase):
    """--chunk i/n：几份合起来正好是整套，不重不漏。"""

    def setUp(self):
        self.cases = [EvalCase(id=f"X{i:02d}", query="q", reference_sql="SELECT 1") for i in range(40)]

    def test_chunks_partition_the_bank(self):
        for count in (1, 3, 7):
            with self.subTest(n=count):
                parts = [select_chunk(self.cases, f"{i}/{count}") for i in range(count)]
                ids = [case.id for part in parts for case in part]
                self.assertEqual(sorted(ids), [case.id for case in self.cases])
                self.assertLessEqual(max(map(len, parts)) - min(map(len, parts)), 1)

    def test_bad_index_is_rejected(self):
        for chunk in ("3/3", "-1/3"):
            with self.subTest(chunk=chunk), self.assertRaises(SystemExit):
                select_chunk(self.cases, chunk)


if __name__ == "__main__":
    unittest.main()
