"""
静默降级告警。

这个项目里最难发现的不是报错，是"链路跑通、退出码 0、输出看着合理，
但中间某一环已经悄悄失效了"。三个真实案例见 docs/排查记录.md：

- 精排名额按小库调的，大库上悄悄漏掉输出字段，表现为模型说"Schema 里没这个字段"
- CoT 正则依赖标点，模型换了个句号就解析失败，表现为一条 SQL 都不生成
- .env 被测试进程读到，单元测试开始打真实 API，表现为"只是有点慢"

共同点是降级发生时没有任何痕迹。这个模块给每一处已知的降级点装上可观测点：
出问题时要么在 stderr 留下一行告警，要么被 PipelineResult.diagnostics 带出来。

用法：

    from askdata_diagnostics import collect, emit, Codes

    with collect() as diagnostics:
        ...                       # 跑链路
    for item in diagnostics:      # 拿到本次运行的所有降级记录
        print(item.render())

注意：collect() 基于 contextvars，只覆盖当前执行上下文。
后台线程（例如记忆模块的异步摘要）里的 emit 仍然会写 logging，
但不会进入调用方的 collect() 列表。
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger("askdata")


class Codes:
    """
    降级码。

    用稳定的机器可读码而不是自由文本，方便日志检索和写断言。
    """

    COT_PARSE_EMPTY = "COT_PARSE_EMPTY"
    """CoT 有输出但一个四元组都没解析出来，后续不会生成任何 SQL。"""

    SCHEMA_RECALL_CAPPED = "SCHEMA_RECALL_CAPPED"
    """精排名额相对候选数过小，可能已经把需要的字段截掉了。"""

    MODEL_MOCK_FALLBACK = "MODEL_MOCK_FALLBACK"
    """没有 API Key，大模型调用降级成写死的 Mock 结果。"""

    RERANK_MOCK_FALLBACK = "RERANK_MOCK_FALLBACK"
    """没有 Rerank 服务，精排降级成本地规则排序。"""

    EMBEDDING_MOCK_FALLBACK = "EMBEDDING_MOCK_FALLBACK"
    """没有 Embedding 服务，向量降级成哈希伪向量，语义召回实际失效。"""

    COLUMN_SAMPLES_FAILED = "COLUMN_SAMPLES_FAILED"
    """字段样例值抽取失败，该字段的索引文本会缺少样例，召回质量下降。"""

    QUERY_REWRITE_SKIPPED = "QUERY_REWRITE_SKIPPED"
    """检测到指代词但没做指代消解，多轮追问会按字面理解，结果大概率不对。"""

    QUERY_REWRITE_FAILED = "QUERY_REWRITE_FAILED"
    """指代消解调用失败，已回退为原始 Query。"""

    EMPTY_RESULT_SET = "EMPTY_RESULT_SET"
    """SQL 执行成功但返回 0 行，筛选条件可能有问题（例如凭空推断的 ID）。"""


@dataclass
class Diagnostic:
    """一条降级记录。"""

    code: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        """渲染成一行可读文本。"""
        if not self.context:
            return f"[{self.code}] {self.message}"

        detail = "，".join(f"{key}={value}" for key, value in self.context.items())
        return f"[{self.code}] {self.message}（{detail}）"


_active: ContextVar[Optional[List[Diagnostic]]] = ContextVar(
    "askdata_diagnostics",
    default=None,
)


def emit(code: str, message: str, **context: Any) -> Diagnostic:
    """
    记录一次降级。

    同时做两件事：写 logging（默认会出现在 stderr，保证不会完全无声），
    以及追加到当前 collect() 的列表里（如果有）。
    """
    diagnostic = Diagnostic(code=code, message=message, context=dict(context))

    bucket = _active.get()
    if bucket is not None:
        bucket.append(diagnostic)

    logger.warning("%s", diagnostic.render())

    return diagnostic


@contextmanager
def collect() -> Iterator[List[Diagnostic]]:
    """
    收集当前上下文里的降级记录。

    Yields:
        List[Diagnostic]: 收集到的记录，退出上下文后仍可读。
    """
    bucket: List[Diagnostic] = []
    token = _active.set(bucket)

    try:
        yield bucket
    finally:
        _active.reset(token)


@contextmanager
def silenced() -> Iterator[None]:
    """
    临时关闭 logging 输出，只保留 collect() 收集。

    单元测试里用它避免刷屏。
    """
    previous = logger.disabled
    logger.disabled = True

    try:
        yield
    finally:
        logger.disabled = previous


class OnceEmitter:
    """
    同一个降级只报一次。

    Mock 降级这类问题，每次调用都报会把日志刷爆，
    但一次都不报又等于没有。按实例报一次是合适的粒度。
    """

    def __init__(self) -> None:
        self._fired: set = set()

    def emit(self, code: str, message: str, **context: Any) -> Optional[Diagnostic]:
        """首次遇到该 code 时上报，之后静默。"""
        if code in self._fired:
            return None

        self._fired.add(code)
        return emit(code, message, **context)
