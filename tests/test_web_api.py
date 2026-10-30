from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型，不加载本地大模型。
# 必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import logging  # noqa: E402

logging.getLogger("askdata").disabled = True

import http.client  # noqa: E402
import json  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest import mock  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from askdata_diagnostics import Codes, silenced  # noqa: E402
from askdata_web.server import (  # noqa: E402
    DATABASE_NAMES,
    MAX_BODY_BYTES,
    SAMPLE_QUESTIONS,
    AskDataService,
    build_parser,
    make_handler,
)
from eval.runner import DATASETS  # noqa: E402

# 没有 Key 时 CoT 和 SQL 走 Mock，这道是 Mock 内置的题，离线就能跑完整条链路
QUERY = "查询总交易笔数大于50000的利率是多少"
CHINOOK_DB = ROOT / "runtime_data" / "chinook.db"


class _WebServer:
    """在随机端口上起一个真实的 Web 服务，trade 数据集，全部走 Mock。"""

    def __init__(self, dataset="trade"):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        with silenced():
            self.service = AskDataService(dataset=dataset, db_path=tmp / "web.db", memory_db=tmp / "memory.db")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        self.address = self.httpd.server_address
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection(*self.address, timeout=10)
        try:
            with silenced():
                conn.request(method, path, body=body, headers=headers or {})
                response = conn.getresponse()
                payload = response.read()
            return response, payload
        finally:
            conn.close()

    def json(self, method, path, body=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        response, payload = self.request(method, path, body, {"Content-Type": "application/json"})
        return response.status, json.loads(payload)

    def raw(self, data: bytes, timeout: float = 3.0) -> bytes:
        """
        原样发一段字节，读到服务端断开或超时。

        有超时：服务端卡在读请求体上时，测试应该很快失败，而不是把整个测试套件挂住。
        """
        sock = socket.create_connection(self.address, timeout=timeout)
        chunks = []
        try:
            sock.sendall(data)
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        except socket.timeout:
            chunks.append(b"<timeout>")
        finally:
            sock.close()
        return b"".join(chunks)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.service.close()
        self._tmp.cleanup()


class WebApiTest(unittest.TestCase):
    """正常路径：页面、健康检查、提问、新会话、出错时的 500。"""

    @classmethod
    def setUpClass(cls):
        cls.server = _WebServer()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def test_index_page(self):
        for path in ("/", "/index.html"):
            with self.subTest(path=path):
                response, body = self.server.request("GET", path)
                self.assertEqual(response.status, 200)
                self.assertIn("text/html", response.getheader("Content-Type"))
                self.assertIn(b"/api/health", body)

    def test_health(self):
        status, payload = self.server.json("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual((payload["dataset"], payload["tables"], payload["columns"]), ("trade", 2, 9))
        self.assertEqual(payload["provider"], "mock")
        self.assertFalse(payload["local_models"])
        self.assertEqual(payload["samples"], SAMPLE_QUESTIONS["trade"])
        self.assertEqual(payload["refusal_sample"], SAMPLE_QUESTIONS["trade"][-1])

    def test_schema_is_available_without_a_query(self):
        status, payload = self.server.json("GET", "/api/schema")
        self.assertEqual(status, 200)
        self.assertEqual(payload["dataset"], "trade")
        tables = {table["name"]: table for table in payload["tables"]}
        self.assertEqual(set(tables), {"trade_summary", "interest_info"})
        columns = {column["name"]: column for column in tables["trade_summary"]["columns"]}
        self.assertTrue(columns["user_id"]["primary_key"])
        self.assertTrue(columns["total_trade_count"]["type"])
        self.assertTrue(payload["relations"])

    def test_frontend_assets_are_served_and_paths_are_allowlisted(self):
        for path, mime_type in (("/static/app.css", "text/css"), ("/static/app.js", "text/javascript")):
            with self.subTest(path=path):
                response, body = self.server.request("GET", path)
                self.assertEqual(response.status, 200)
                self.assertIn(mime_type, response.getheader("Content-Type"))
                self.assertTrue(body)
        for path in ("/static/../server.py", "/static/.env", "/static/nope.js"):
            with self.subTest(path=path):
                response, _ = self.server.request("GET", path)
                self.assertEqual(response.status, 404)

    def test_query_string_does_not_change_the_route(self):
        status, payload = self.server.json("GET", "/api/health?t=1")
        self.assertEqual((status, payload["dataset"]), (200, "trade"))

    def test_unknown_paths_are_404(self):
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                status, payload = self.server.json(method, "/api/nope", {} if method == "POST" else None)
                self.assertEqual((status, payload), (404, {"error": "not found"}))

    def test_ask_returns_the_pipeline_trace(self):
        status, payload = self.server.json("POST", "/api/ask", {"query": QUERY, "session_id": "t-ask"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["query"], QUERY)
        self.assertTrue(payload["queried_database"])
        self.assertTrue(payload["answer"])

        self.assertEqual({table["name"] for table in payload["schema_tables"]}, {"trade_summary", "interest_info"})
        self.assertIn(Codes.MODEL_MOCK_FALLBACK, {item["code"] for item in payload["diagnostics"]})

        step = payload["steps"][-1]
        self.assertTrue(step["success"])
        self.assertIn("interest_rate", step["sql"])
        self.assertEqual(step["columns"], ["interest_rate"])
        self.assertEqual((len(step["rows"]), step["row_count"], step["truncated"]), (5, 5, False))

        self.assertTrue(payload["plan"])
        self.assertEqual(set(payload["plan"][0]), {"step", "database", "objects", "instruction", "output", "missing"})
        self.assertFalse(any(item["missing"] for item in payload["plan"]))

    def test_refusal_plan_is_marked_missing(self):
        """规划判定库里缺数据时，界面靠 plan[].missing 认出拒答，并把处理对象当原因展示。"""
        cot = (
            "步骤1：\n(\n  数据库：缺失,\n"
            "  处理对象：缺少用户信用评分字段；trade_summary 只有交易汇总,\n"
            "  操作指令：确认 Schema 中没有信用评分,\n  输出目标：缺失\n)"
        )
        result = SimpleNamespace(keywords=[], rewritten_query="", schema_context="", cot_output=cot, diagnostics=[], step_logs=[])
        routed = SimpleNamespace(
            decision=SimpleNamespace(route=SimpleNamespace(value="text2sql"), reason=""),
            queried_database=True, answer="", pipeline_result=result,
        )
        with mock.patch.object(self.server.service.service, "run", return_value=routed):
            status, payload = self.server.json("POST", "/api/ask", {"query": "每个用户的信用评分是多少"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["steps"], [])
        [step] = payload["plan"]
        self.assertTrue(step["missing"])
        self.assertTrue(step["objects"].startswith("缺少用户信用评分字段；trade_summary"))

    def test_truncation_reaches_the_page(self):
        executor = self.server.service.pipeline.mcp_router.executors["trade_db"]
        with mock.patch.object(executor, "max_rows", 2):
            status, payload = self.server.json("POST", "/api/ask", {"query": QUERY, "session_id": "t-cut"})
        self.assertEqual(status, 200)
        step = payload["steps"][-1]
        self.assertEqual((len(step["rows"]), step["row_count"], step["truncated"]), (2, 2, True))
        self.assertIn(Codes.RESULT_TRUNCATED, {item["code"] for item in payload["diagnostics"]})

    def test_empty_query_is_rejected(self):
        for body in ({}, {"query": ""}, {"query": "   "}):
            with self.subTest(body=body):
                status, payload = self.server.json("POST", "/api/ask", body)
                self.assertEqual((status, payload["error"]), (400, "问题不能为空"))

    def test_reset_starts_a_new_session(self):
        first = self.server.json("POST", "/api/reset", {})
        second = self.server.json("POST", "/api/reset", {})
        self.assertEqual((first[0], second[0]), (200, 200))
        self.assertTrue(first[1]["session_id"].startswith("web-"))
        self.assertNotEqual(first[1]["session_id"], second[1]["session_id"])

    def test_pipeline_error_is_returned_as_500_json(self):
        """异常如实交给前端，不要静默吞掉，也不能让连接直接断开。"""
        with mock.patch.object(self.server.service, "ask", side_effect=RuntimeError("HTTP Error 402: Payment Required")):
            status, payload = self.server.json("POST", "/api/ask", {"query": QUERY})
        self.assertEqual(status, 500)
        self.assertEqual(payload["error"], "RuntimeError: HTTP Error 402: Payment Required")
        self.assertIn("余额不足", payload["hint"])


class WebApiBadRequestTest(unittest.TestCase):
    """
    不合法的请求体要回 4xx。

    原先：不是 JSON 对象、不是合法 UTF-8、Content-Length 不是数字，处理线程抛异常，连接断开，
    前端收不到任何响应；Content-Length 是负数或声称很大，服务端一直等着读，请求卡住。
    """

    @classmethod
    def setUpClass(cls):
        cls.server = _WebServer()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def post_raw(self, body: bytes, length: str) -> bytes:
        return self.server.raw(
            b"POST /api/ask HTTP/1.1\r\nHost: test\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {length}\r\n\r\n".encode()
            + body
        )

    def assert_status(self, reply: bytes, status: int):
        self.assertNotIn(b"<timeout>", reply, "服务端卡住了")
        self.assertTrue(reply.startswith(f"HTTP/1.1 {status} ".encode()), reply[:80])

    def test_body_that_is_not_a_json_object(self):
        for body in (b"[1, 2]", b'"x"', b"3", b"null"):
            with self.subTest(body=body):
                status, payload = self.server.json("POST", "/api/ask", body)
                self.assertEqual((status, payload["error"]), (400, "请求体必须是 JSON 对象"))

    def test_body_that_is_not_json(self):
        for body in (b"{oops", b"\xff\xfe{}"):
            with self.subTest(body=body):
                status, payload = self.server.json("POST", "/api/ask", body)
                self.assertEqual((status, payload["error"]), (400, "请求体不是合法 JSON"))

    def test_content_length_that_is_not_a_number(self):
        reply = self.post_raw(b"{}", "abc")
        self.assert_status(reply, 400)
        self.assertIn(b"Connection: close", reply)

    def test_negative_content_length(self):
        reply = self.post_raw(b"{}", "-1")
        self.assert_status(reply, 400)
        self.assertIn(b"Connection: close", reply)

    def test_oversized_body_is_refused_without_reading_it(self):
        reply = self.post_raw(b"{}", str(MAX_BODY_BYTES + 1))
        self.assert_status(reply, 413)
        self.assertIn(b"Connection: close", reply)

    def test_connection_is_reusable_after_a_bad_json_body(self):
        """请求体读完了才报错，连接还能接着用，下一个请求不会被错位解析。"""
        bad = b"{oops"
        reply = self.server.raw(
            b"POST /api/ask HTTP/1.1\r\nHost: test\r\n"
            + f"Content-Length: {len(bad)}\r\n\r\n".encode() + bad
            + b"GET /api/health HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n"
        )
        self.assertNotIn(b"<timeout>", reply)
        self.assertEqual(reply.count(b"HTTP/1.1 "), 2)
        self.assertTrue(reply.startswith(b"HTTP/1.1 400 "))
        self.assertIn(b"HTTP/1.1 200 ", reply)


class WebDatasetTest(unittest.TestCase):
    """Web 能选的数据集和评测器一致，每套都有示例问题。原先只能选 ecommerce 和 trade。"""

    def test_database_names_match_the_eval_runner(self):
        for dataset, (_, database_name, _) in DATASETS.items():
            with self.subTest(dataset=dataset):
                self.assertEqual(DATABASE_NAMES[dataset], database_name)

    def test_every_dataset_has_samples_and_a_cli_choice(self):
        self.assertEqual(set(SAMPLE_QUESTIONS), set(DATABASE_NAMES))
        self.assertTrue(all(SAMPLE_QUESTIONS.values()))
        dataset_action = next(item for item in build_parser()._actions if item.dest == "dataset")
        self.assertEqual(set(dataset_action.choices), set(DATABASE_NAMES))

    def test_unknown_dataset_is_rejected(self):
        with self.assertRaises(ValueError):
            AskDataService(dataset="nope", db_path=Path("unused.db"), memory_db=Path("unused-memory.db"))

    def check_dataset(self, dataset, tables):
        """SQL 按库名路由到执行器：库名错了，CoT 写的数据库和执行器对不上。"""
        server = _WebServer(dataset=dataset)
        try:
            status, payload = server.json("GET", "/api/health")
            executors = list(server.service.pipeline.mcp_router.executors)
        finally:
            server.close()
        self.assertEqual((status, payload["dataset"], payload["tables"]), (200, dataset, tables))
        self.assertEqual(executors, [DATABASE_NAMES[dataset]])
        self.assertEqual(payload["samples"], SAMPLE_QUESTIONS[dataset])

    def test_generated_datasets(self):
        for dataset, tables in (("trade", 2), ("ecommerce", 11), ("ecommerce_big", 88)):
            with self.subTest(dataset=dataset):
                self.check_dataset(dataset, tables)

    @unittest.skipUnless(CHINOOK_DB.is_file(), "没有 runtime_data/chinook.db（不进仓库，CI 上没有）")
    def test_chinook(self):
        with mock.patch.dict(os.environ, {"CHINOOK_DB": str(CHINOOK_DB)}):
            self.check_dataset("chinook", 11)


if __name__ == "__main__":
    unittest.main()
