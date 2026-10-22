from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import logging  # noqa: E402

logging.getLogger("askdata").disabled = True

import http.client  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
import urllib.error  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_diagnostics import Codes, collect, silenced  # noqa: E402
from cot_planning.thinking_client import ThinkingModelClient, ThinkingModelConfig  # noqa: E402
from llm_http import open_stream, post_json  # noqa: E402
from sql_generation.coder_client import CoderModelClient, CoderModelConfig  # noqa: E402

OK_BODY = {"choices": [{"message": {"content": "SELECT 1"}}]}


class _Server:
    """按顺序回放脚本里的响应：(状态码, 响应头, 响应体, 先睡几秒)。记下收到的每个请求。"""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.requests.append((dict(self.headers), json.loads(body)))
                status, headers, payload, delay = outer.script.pop(0) if outer.script else (200, {}, OK_BODY, 0)
                if delay:
                    time.sleep(delay)
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                if "Content-Length" not in headers:   # 脚本里写了就照写：声称的比实际长，客户端读到 IncompleteRead
                    self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/chat"
        # 默认每 0.5 秒才看一次关闭信号，十几个测试服务累加起来要好几秒
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def truncated():
    """拿到了 200 和响应头，正文一个字节没给就断了：客户端读到 IncompleteRead(0 bytes read)。"""
    return (200, {"Content-Length": "100", "Connection": "close"}, b"", 0)


def busy(status, retry_after=None):
    return (status, {"Retry-After": retry_after} if retry_after else {}, {"error": "busy"}, 0)


class PostJsonRetryTest(unittest.TestCase):
    def serve(self, *script):
        server = _Server(script)
        self.addCleanup(server.close)
        return server

    def call(self, server, timeout=5):
        sleeps = []
        with collect() as diagnostics, silenced():
            try:
                result = post_json(server.url, {"q": 1}, "sk-test", timeout, sleep=sleeps.append)
            except Exception as exc:
                result = exc
        return result, sleeps, [d.code for d in diagnostics]

    def test_429_with_retry_after_then_success(self):
        server = self.serve(busy(429, "2"))
        result, sleeps, codes = self.call(server)
        self.assertEqual(result, OK_BODY)
        self.assertEqual(sleeps, [2.0])
        self.assertEqual(codes, [Codes.MODEL_CALL_RETRIED])
        self.assertEqual(len(server.requests), 2)

    def test_5xx_backs_off_then_gives_up_with_the_original_error(self):
        server = self.serve(busy(503), busy(502), busy(500), busy(504))
        result, sleeps, _ = self.call(server)
        self.assertIsInstance(result, urllib.error.HTTPError)
        self.assertEqual(result.code, 504)
        self.assertEqual(sleeps, [1.0, 2.0, 4.0])
        self.assertEqual(len(server.requests), 4)

    def test_persistent_4xx_is_not_retried(self):
        """402 余额耗尽、401 Key 失效：再试一百次也一样。报错文本保持原样，评测器靠它熔断。"""
        for status in (400, 401, 402, 403):
            with self.subTest(status=status):
                server = self.serve(busy(status))
                result, sleeps, codes = self.call(server)
                self.assertIsInstance(result, urllib.error.HTTPError)
                self.assertIn(f"HTTP Error {status}", str(result))
                self.assertEqual((sleeps, codes, len(server.requests)), ([], [], 1))

    def test_retry_after_is_capped(self):
        server = self.serve(busy(429, "600"))
        _, sleeps, _ = self.call(server)
        self.assertEqual(sleeps, [30.0])

    def test_unparseable_retry_after_falls_back_to_backoff(self):
        server = self.serve(busy(429, "Wed, 21 Oct 2015 07:28:00 GMT"))
        _, sleeps, _ = self.call(server)
        self.assertEqual(sleeps, [1.0])

    def test_timeout_is_retried(self):
        server = self.serve((200, {}, OK_BODY, 0.3))
        result, sleeps, codes = self.call(server, timeout=0.1)
        self.assertEqual(result, OK_BODY)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(codes, [Codes.MODEL_CALL_RETRIED])

    def test_truncated_body_is_retried(self):
        """
        第七套之后的一次回归里，IncompleteRead(0 bytes read) 出现了几十次。原先重试只包住建立连接，
        读响应体时断了直接抛出去。
        """
        server = self.serve(truncated())
        result, sleeps, codes = self.call(server)
        self.assertEqual(result, OK_BODY)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(codes, [Codes.MODEL_CALL_RETRIED])
        self.assertEqual(len(server.requests), 2)

    def test_truncated_body_every_time_gives_up_with_the_original_error(self):
        server = self.serve(truncated(), truncated(), truncated(), truncated())
        result, sleeps, _ = self.call(server)
        self.assertIsInstance(result, http.client.IncompleteRead)
        self.assertEqual(sleeps, [1.0, 2.0, 4.0])
        self.assertEqual(len(server.requests), 4)

    def test_body_that_is_not_json_is_not_retried(self):
        """正文完整但不是 JSON：不是"等一等就会好"的问题，重试也一样。"""
        server = self.serve((200, {}, b"<html>oops</html>", 0))
        result, sleeps, _ = self.call(server)
        self.assertIsInstance(result, json.JSONDecodeError)
        self.assertEqual((sleeps, len(server.requests)), ([], 1))

    def test_sends_bearer_key_and_json(self):
        server = self.serve()
        self.call(server)
        headers, body = server.requests[0]
        self.assertEqual(headers["Authorization"], "Bearer sk-test")
        self.assertEqual(body, {"q": 1})


class StreamAndClientWiringTest(unittest.TestCase):
    def serve(self, *script):
        server = _Server(script)
        self.addCleanup(server.close)
        return server

    def test_open_stream_retries_before_streaming(self):
        lines = b'data: {"choices":[{"delta":{"content":"ab"}}]}\n\ndata: [DONE]\n\n'
        server = self.serve(busy(429, "1"), (200, {"Content-Type": "text/event-stream"}, lines, 0))
        sleeps = []
        with silenced(), open_stream(server.url, {}, "k", 5, sleep=sleeps.append) as response:
            body = response.read()
        self.assertEqual(body, lines)
        self.assertEqual(sleeps, [1.0])

    def test_coder_client_survives_a_429(self):
        server = self.serve(busy(429, "0"))
        client = CoderModelClient(CoderModelConfig(api_key="k", base_url=server.url, model="m"))
        with silenced():
            self.assertEqual(client.generate_sql("p"), "SELECT 1")
        self.assertEqual(len(server.requests), 2)

    def test_thinking_client_survives_a_truncated_body(self):
        """CoT 规划走的是非流式调用，回归里报 IncompleteRead 最多的就是它。"""
        server = self.serve(truncated())
        client = ThinkingModelClient(ThinkingModelConfig(api_key="k", base_url=server.url, model="m"))
        with silenced():
            self.assertEqual(client.generate("p"), "SELECT 1")
        self.assertEqual(len(server.requests), 2)

    def test_thinking_client_stream_survives_a_429(self):
        lines = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
        server = self.serve(busy(429, "0"), (200, {}, lines, 0))
        client = ThinkingModelClient(ThinkingModelConfig(api_key="k", base_url=server.url, model="m"))
        with silenced():
            self.assertEqual("".join(client.generate_stream("p")), "ok")

    def test_client_error_keeps_the_original_text(self):
        server = self.serve(busy(402))
        client = CoderModelClient(CoderModelConfig(api_key="k", base_url=server.url, model="m"))
        with silenced(), self.assertRaises(RuntimeError) as caught:
            client.generate_sql("p")
        self.assertIn("HTTP Error 402: Payment Required", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
