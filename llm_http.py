"""
调模型接口的 HTTP 请求：所有客户端共用一份，429 和 5xx 自动退避重试。

原先 7 个客户端（思考模型的普通和流式调用、SQL 生成、关键词抽取、指代消解、阿里云精排和
向量）各自拼一遍请求、各自 urlopen，谁都不重试。评测器会把整道题重跑，所以评测里接得住；
Web 界面和直接调用链路时，一次 429 就是一次报错。第四套留出集首次运行 6 个进程并行，
就撞上过 429。

重试只管"等一等就会好"的：

    429、500、502、503、504          重试；有 Retry-After 就按它等
    超时、连接被重置、对端提前断开     重试
    读响应体时断了（IncompleteRead）  重试——拿到了响应头、正文没读完。第七套之后的一次回归里
                                      出现了几十次 IncompleteRead(0 bytes read)，原先不重试，
                                      靠评测器把整道题重跑才接住；Web 界面上就是一次报错
    400、401、402、403 等其余 4xx     不重试——Key 失效、余额耗尽，再试一百次也一样

报错文本保持 urllib 的原文（"HTTP Error 402: Payment Required"）：评测器靠这些字样
区分持续性故障和瞬时故障，决定熔断。
"""

from __future__ import annotations

import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from askdata_diagnostics import Codes, emit

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_SECONDS = (1.0, 2.0, 4.0)
MAX_RETRY_AFTER = 30.0


def post_json(
    url: str,
    payload: dict,
    api_key: str,
    timeout: float,
    *,
    label: str = "模型",
    max_retries: int = MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """POST 一个 JSON，返回解析后的 JSON。失败时抛出最后一次的原始异常。"""
    request = _build_request(url, payload, api_key)

    def read(response):
        return json.loads(response.read().decode("utf-8"))

    return _with_retry(request, timeout, read, label, max_retries, sleep)


def open_stream(
    url: str,
    payload: dict,
    api_key: str,
    timeout: float,
    *,
    label: str = "模型",
    max_retries: int = MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
):
    """
    打开一个流式请求，返回 response（调用方负责 with / 逐行读）。

    只在建立连接时重试：429、5xx 在拿到响应头时就会抛出来。流已经开始往外吐内容以后
    再断，就不重试了——前半截已经交给调用方，重来会重复。
    """
    request = _build_request(url, payload, api_key, accept="text/event-stream")
    return _with_retry(request, timeout, lambda response: response, label, max_retries, sleep, close=False)


def _build_request(url: str, payload: dict, api_key: str, accept: Optional[str] = None):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if accept:
        headers["Accept"] = accept

    return urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def _with_retry(request, timeout, handle, label, max_retries, sleep, close=True):
    for attempt in range(max_retries + 1):
        try:
            response = urllib.request.urlopen(request, timeout=timeout)

            if not close:
                # 流式：只管建立连接。读是调用方的事，流开始以后再断不重试
                return handle(response)

            # 非流式：读响应体也在重试范围里——正文没读完就断（IncompleteRead）时，
            # 还什么都没交给调用方，重来不会重复
            with response:
                return handle(response)
        except Exception as exc:
            delay = _retry_delay(exc, attempt)

            if delay is None or attempt >= max_retries:
                raise

            emit(
                Codes.MODEL_CALL_RETRIED,
                f"{label}接口暂时不可用，等 {delay:g} 秒后重试",
                第几次=attempt + 1,
                原因=(str(exc) or type(exc).__name__)[:80],
            )
            sleep(delay)

    raise AssertionError("unreachable")


def _retry_delay(exc: Exception, attempt: int) -> Optional[float]:
    """该重试就返回要等几秒，不该重试返回 None。"""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code not in RETRY_STATUS:
            return None

        retry_after = _parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
        if retry_after is not None:
            return min(retry_after, MAX_RETRY_AFTER)

        return BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]

    transient = (
        socket.timeout, TimeoutError, ConnectionResetError,
        http.client.RemoteDisconnected, http.client.IncompleteRead,
    )
    reason = getattr(exc, "reason", None)  # URLError 把底层异常包在 reason 里

    if isinstance(exc, transient) or isinstance(reason, transient):
        return BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]

    return None


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Retry-After 只认秒数；HTTP 日期格式少见，认不出就按退避表来。"""
    if not value:
        return None

    try:
        seconds = float(value.strip())
    except ValueError:
        return None

    return max(0.0, seconds)
