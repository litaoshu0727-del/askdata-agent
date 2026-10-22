"""
AskData Web 服务。

用标准库的 http.server，不引 Flask/FastAPI——整个项目的核心链路
只依赖 numpy + 标准库，这一层没理由破坏这个性质。

启动：
    python -m askdata_web.server
    python -m askdata_web.server --port 8080 --dataset chinook

接口：
    GET  /               界面
    GET  /api/health     供应商、数据集、降级状态
    POST /api/ask        提问，返回整条链路的中间产物
    POST /api/reset      清空当前会话记忆
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_memory import (  # noqa: E402
    ConversationMemoryService,
    MemoryServiceConfig,
    ShortTermMemoryConfig,
)
from askdata_pipeline.dynamic_service import DynamicAskDataService  # noqa: E402
from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402
from llm_config import describe_chat_provider, resolve_chat_provider, use_local_models  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"

# 整条链路是同步的，同一时刻只服务一个请求，避免多人同时问把记忆搅乱
_LOCK = threading.Lock()

# 问题只有几百字。上限之外的请求体不读，直接 413 并断开连接
MAX_BODY_BYTES = 1 << 20

# 数据集 → 库名，和 eval/runner.py 的 DATASETS 一致
DATABASE_NAMES = {
    "ecommerce": "ecommerce_db",
    "ecommerce_big": "ecommerce_big_db",
    "chinook": "chinook_db",
    "sakila": "sakila_db",
    "trade": "trade_db",
}

# 界面上的示例问题，按数据集给。每套最后两道：追问（测指代消解）、库里没有的数据（测诚实拒答）
SAMPLE_QUESTIONS = {
    "ecommerce": [
        "销售额最高的三个店铺，店铺名称和销售额分别是多少",
        "客单价最高的10个用户，他们的用户ID和客单价分别是多少",
        "因为商品质量问题退款的总金额是多少",
        "它们的退款金额分别是多少",
        "每个用户的具体年龄是多少岁",
    ],
    "chinook": [
        "曲目数最多的 5 个流派，各有多少首曲目",
        "每位销售支持员工负责多少位客户",
        "发票金额合计最高的 3 个国家是哪些",
        "它们各有多少位客户",
        "每位客户的年龄是多少岁",
    ],
    "sakila": [
        "每家门店各有多少位客户",
        "租借次数最多的 5 部影片是哪些，各租了多少次",
        "每个影片分类的营业额是多少",
        "它们各有多少部影片",
        "每部影片的豆瓣评分是多少",
    ],
    "trade": [
        "查询总交易笔数大于50000的利率是多少",
        "活跃天数最多的 5 个用户，他们的交易总金额分别是多少",
        "它们的利率类型分别是什么",
        "每个用户的信用评分是多少",
    ],
}
SAMPLE_QUESTIONS["ecommerce_big"] = SAMPLE_QUESTIONS["ecommerce"]


def parse_schema_context(text: str) -> List[Dict[str, Any]]:
    """
    把 SchemaGraph 的文本上下文解析成结构化数据，供前端渲染。

    直接把整段文本丢给前端也能显示，但那样就只是一个代码块；
    拆成表和字段之后才能做高亮、折叠这些真正有用的交互。
    """
    tables: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    current_column: Optional[Dict[str, Any]] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        table_match = re.match(r"^表名[：:]\s*(\S+)", stripped)
        if table_match:
            current = {"name": table_match.group(1), "summary": "", "columns": []}
            tables.append(current)
            current_column = None
            continue

        if current is None:
            continue

        summary_match = re.match(r"^表格摘要[：:]\s*(.+)", stripped)
        if summary_match:
            current["summary"] = summary_match.group(1)
            continue

        column_match = re.match(r"^-\s*字段名[：:]\s*(\S+)", stripped)
        if column_match:
            current_column = {"name": column_match.group(1), "desc": "", "role": ""}
            current["columns"].append(current_column)
            continue

        if current_column is not None:
            desc_match = re.match(r"^字段含义[：:]\s*(.+)", stripped)
            if desc_match:
                current_column["desc"] = desc_match.group(1)
                continue

            role_match = re.match(r"^字段角色[：:]\s*(.+)", stripped)
            if role_match:
                current_column["role"] = role_match.group(1)

    return tables


def parse_relations(text: str) -> List[str]:
    """从 Schema 文本里抽出表关联关系。"""
    relations: List[str] = []
    in_section = False

    for raw_line in text.splitlines():
        stripped = raw_line.strip()

        if stripped.startswith("表关联关系"):
            in_section = True
            continue

        if in_section:
            if stripped.startswith("- "):
                relations.append(stripped[2:])
            elif stripped and not stripped.startswith("-"):
                in_section = False

    return relations


class AskDataService:
    """把管线、记忆和路由包成一个可复用的服务对象。"""

    def __init__(self, dataset: str, db_path: Path, memory_db: Path):
        if dataset not in DATABASE_NAMES:
            raise ValueError(f"未知数据集 {dataset}，可选：{'、'.join(DATABASE_NAMES)}")

        self.dataset = dataset
        database_name = DATABASE_NAMES[dataset]

        self.pipeline = AskDataText2SQLPipeline(
            PipelineConfig(
                dataset=dataset,
                database_name=database_name,
                db_path=db_path,
                sample_size=5,
            )
        )

        self.memory = ConversationMemoryService(
            MemoryServiceConfig(
                db_path=memory_db,
                short_term=ShortTermMemoryConfig(
                    max_window_messages=8,
                    max_window_tokens=4000,
                    async_summary=True,
                ),
            )
        )

        self.service = DynamicAskDataService(
            pipeline=self.pipeline,
            memory=self.memory,
        )

    def health(self) -> Dict[str, Any]:
        provider = resolve_chat_provider()
        table_count = len(self.pipeline.schema_retrieval_service.tables)
        column_count = len(self.pipeline.schema_retrieval_service.columns)

        return {
            "dataset": self.dataset,
            "tables": table_count,
            "columns": column_count,
            "provider": provider.provider or "mock",
            "model": provider.model if provider.available else "",
            "provider_text": describe_chat_provider(),
            "local_models": use_local_models(),
            "setup_diagnostics": [item.render() for item in self.pipeline.setup_diagnostics],
            "samples": SAMPLE_QUESTIONS[self.dataset],
        }

    def ask(self, query: str, user_id: str, session_id: str) -> Dict[str, Any]:
        started = time.time()

        routed = self.service.run(
            user_id=user_id,
            session_id=session_id,
            query=query,
            enable_long_term=True,
        )

        payload: Dict[str, Any] = {
            "query": query,
            "route": routed.decision.route.value,
            "route_reason": routed.decision.reason,
            "queried_database": routed.queried_database,
            "answer": routed.answer,
            "elapsed": round(time.time() - started, 1),
            "keywords": [],
            "rewritten_query": "",
            "schema_tables": [],
            "relations": [],
            "cot": "",
            "steps": [],
            "diagnostics": [],
        }

        result = routed.pipeline_result

        if result is not None:
            payload["keywords"] = list(result.keywords)
            payload["rewritten_query"] = result.rewritten_query
            payload["schema_tables"] = parse_schema_context(result.schema_context)
            payload["relations"] = parse_relations(result.schema_context)
            payload["cot"] = result.cot_output
            payload["diagnostics"] = [
                {"code": item.code, "text": item.render()}
                for item in result.diagnostics
            ]
            payload["steps"] = [
                {
                    "sql": log.sql,
                    "success": bool(log.execution_result.get("success")),
                    "columns": log.execution_result.get("columns") or [],
                    "rows": (log.execution_result.get("rows") or [])[:200],
                    "row_count": log.execution_result.get("row_count") or 0,
                    "truncated": bool(log.execution_result.get("truncated")),
                    "error": log.execution_result.get("error"),
                }
                for log in result.step_logs
            ]

        return payload

    @staticmethod
    def new_session() -> str:
        """
        开一个新会话。

        不清空旧会话的记忆——短期记忆本身就是审计痕迹，删掉没有好处。
        换一个 session_id 就等于开一段新对话，旧的留在库里。
        """
        return f"web-{uuid.uuid4().hex[:12]}"

    def close(self) -> None:
        self.memory.close()


def make_handler(service: AskDataService):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # noqa: A003
            # 默认的 stderr 访问日志会把降级告警冲掉，这里静音
            pass

        def _send(self, status: int, body: bytes, content_type: str, close: bool = False) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if close:
                # 请求体没读完就回了错误：连接不能再复用，剩下的字节会被当成下一个请求
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Dict[str, Any], close: bool = False) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8", close=close)

        def _read_json(self) -> Optional[Dict[str, Any]]:
            """
            读请求体，返回 JSON 对象。不合法时已经回了 4xx，返回 None。

            原先 int(Content-Length) 直接用：不是数字、不是合法 UTF-8、不是 JSON 对象，处理线程
            抛异常，连接断开，前端收不到任何响应；负数或声称很大时，服务端一直等着读，
            请求卡住直到客户端断开。
            """
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._json(400, {"error": "Content-Length 不是整数"}, close=True)
                return None

            if length < 0:
                self._json(400, {"error": "Content-Length 不能是负数"}, close=True)
                return None

            if length > MAX_BODY_BYTES:
                self._json(413, {"error": f"请求体超过 {MAX_BODY_BYTES} 字节"}, close=True)
                return None

            raw = self.rfile.read(length) if length else b""

            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(400, {"error": "请求体不是合法 JSON"})
                return None

            if not isinstance(data, dict):
                self._json(400, {"error": "请求体必须是 JSON 对象"})
                return None

            return data

        def do_GET(self):  # noqa: N802
            path = urlsplit(self.path).path

            if path in {"/", "/index.html"}:
                html = (STATIC_DIR / "index.html").read_bytes()
                self._send(200, html, "text/html; charset=utf-8")
                return

            if path == "/api/health":
                self._json(200, service.health())
                return

            self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            path = urlsplit(self.path).path
            data = self._read_json()

            if data is None:
                return

            user_id = str(data.get("user_id") or "web-user")
            session_id = str(data.get("session_id") or "web-session")

            if path == "/api/reset":
                self._json(200, {"session_id": service.new_session()})
                return

            if path == "/api/ask":
                query = str(data.get("query") or "").strip()

                if not query:
                    self._json(400, {"error": "问题不能为空"})
                    return

                try:
                    with _LOCK:
                        payload = service.ask(query, user_id, session_id)
                except Exception as exc:  # 把异常如实交给前端，不要静默吞掉
                    self._json(500, {
                        "error": f"{type(exc).__name__}: {exc}",
                        "hint": "常见原因：API Key 未配置、余额不足、网络不通",
                    })
                    return

                self._json(200, payload)
                return

            self._json(404, {"error": "not found"})

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AskData Web 服务")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--dataset", default="ecommerce", choices=list(DATABASE_NAMES),
        help="ecommerce_big 是 1076 个字段的压测库；chinook 要先把库放到 runtime_data/chinook.db",
    )
    parser.add_argument("--db-path", default="")
    parser.add_argument(
        "--memory-db", default=str(Path("runtime_data") / "web_memory.db")
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    # 降级告警走 stderr，和访问日志分开，方便观察链路状态
    logging.basicConfig(level=logging.WARNING, format="[降级] %(message)s")

    db_path = Path(args.db_path) if args.db_path else (
        Path("runtime_data") / f"{args.dataset}_web.db"
    )

    print(f"正在初始化 {args.dataset} 数据集与检索索引……", flush=True)
    service = AskDataService(
        dataset=args.dataset,
        db_path=db_path,
        memory_db=Path(args.memory_db),
    )

    health = service.health()
    print(f"数据集  {health['dataset']}：{health['tables']} 表 / {health['columns']} 字段")
    print(f"模型    {health['provider_text']}")
    print(f"本地向量与精排  {'已启用' if health['local_models'] else '未启用（走 Mock）'}")

    server = ThreadingHTTPServer((args.host, args.port), make_handler(service))
    # flush：输出被重定向到文件或管道时是整块缓冲的，不刷就看不到服务已经起来了
    print(f"\n启动完成：http://{args.host}:{args.port}\n", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭……")
    finally:
        server.server_close()
        service.close()


if __name__ == "__main__":
    main()
