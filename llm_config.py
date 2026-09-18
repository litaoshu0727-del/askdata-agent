"""
LLM Provider 统一配置。

原始代码把阿里云百炼的接口地址、模型名和 DASHSCOPE_API_KEY 分散写死在 4 个 Client 里，
换一家供应商要改 4 处、还有 4 处拿 DASHSCOPE_API_KEY 当"要不要走 Mock"的开关。
这里把它收敛成一个 provider 无关的入口。

优先级：
    DEEPSEEK_API_KEY  >  DASHSCOPE_API_KEY  >  都没有（各 Client 自动降级到 Mock）

支持的环境变量：
    DEEPSEEK_API_KEY / DEEPSEEK_CHAT_URL / DEEPSEEK_MODEL
    DASHSCOPE_API_KEY / DASHSCOPE_CHAT_URL / DASHSCOPE_CHAT_MODEL
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

DEEPSEEK_DEFAULT_CHAT_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_DEFAULT_MODEL = "deepseek-flash"

DASHSCOPE_DEFAULT_CHAT_URL = (
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)
DASHSCOPE_DEFAULT_MODEL = "qwen-plus"


# ---------------------------------------------------------------------------
# .env 支持
# ---------------------------------------------------------------------------

_DOTENV_LOADED = False


def _parse_dotenv_line(line: str) -> Optional[tuple]:
    """
    解析 .env 的一行，返回 (key, value)；不是有效配置行则返回 None。

    支持的写法：
        KEY=value
        KEY="value"
        KEY='value'
        export KEY=value
        # 注释行
    """
    line = line.strip()

    if not line or line.startswith("#"):
        return None

    if line.startswith("export "):
        line = line[len("export "):].strip()

    if "=" not in line:
        return None

    key, _, value = line.partition("=")
    key = key.strip()

    if not key:
        return None

    value = value.strip()

    # 去掉成对的引号
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]

    return key, value


def load_dotenv(path: Optional[Path] = None, override: bool = False) -> int:
    """
    读取 .env 文件并写入 os.environ。

    不引入 python-dotenv 依赖，二十来行自己解析，避免为了读个配置文件
    给项目加一个第三方包。

    Args:
        path: .env 路径。为空时依次尝试当前工作目录和本文件所在目录。
        override: 是否覆盖已存在的环境变量。默认 False，
            即命令行里 export 的值优先于 .env，符合惯例。

    Returns:
        int: 实际写入的变量个数。
    """
    candidates = []

    if path is not None:
        candidates.append(Path(path))
    else:
        candidates.append(Path.cwd() / ".env")
        candidates.append(Path(__file__).resolve().parent / ".env")

    loaded = 0

    for candidate in candidates:
        if not candidate.is_file():
            continue

        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            parsed = _parse_dotenv_line(raw_line)

            if parsed is None:
                continue

            key, value = parsed

            if not override and os.getenv(key) is not None:
                continue

            os.environ[key] = value
            loaded += 1

        break

    return loaded


def ensure_dotenv_loaded() -> None:
    """
    进程内只加载一次 .env。

    设置 ASKDATA_DISABLE_DOTENV=1 可以完全跳过 .env，
    单元测试靠它保持离线、不读到本机的真实 Key。
    """
    global _DOTENV_LOADED

    if _DOTENV_LOADED:
        return

    _DOTENV_LOADED = True

    if os.getenv("ASKDATA_DISABLE_DOTENV", "").strip().lower() in {"1", "true", "yes", "on"}:
        return

    load_dotenv()


@dataclass
class ChatProviderConfig:
    """
    一次 Chat Completions 调用所需的 provider 配置。

    三家供应商都用 OpenAI 兼容格式，差异只在 chat_url、model 和
    provider 特有的 extra_payload 上。
    """

    provider: str = ""
    """供应商标识：deepseek / dashscope / 空字符串（无可用 Key）。"""

    api_key: str = ""
    """API Key。为空表示没有可用供应商，调用方应降级到 Mock。"""

    chat_url: str = DASHSCOPE_DEFAULT_CHAT_URL
    """Chat Completions 接口地址。"""

    model: str = DASHSCOPE_DEFAULT_MODEL
    """模型名称。"""

    extra_payload: Dict[str, Any] = field(default_factory=dict)
    """供应商特有的请求体字段，会被合并进标准 OpenAI payload。"""

    @property
    def available(self) -> bool:
        """是否有可用的 API Key。"""
        return bool(self.api_key)


def resolve_chat_provider(thinking: Optional[bool] = None) -> ChatProviderConfig:
    """
    按优先级解析当前可用的 Chat 供应商。

    Args:
        thinking: 是否开启思考模式，仅对 DeepSeek 生效。
            True  —— 显式开启，用于 CoT 规划这类需要推理的场景。
            False —— 显式关闭，用于 SQL 生成、关键词抽取这类需要确定性输出的场景。
                     DeepSeek 在思考模式下会忽略 temperature，
                     所以想让 temperature=0.0 真正生效，必须显式关掉。
            None  —— 不干预，使用供应商默认行为（DeepSeek 默认开启思考）。

    Returns:
        ChatProviderConfig: 解析结果。api_key 为空表示应走 Mock。
    """
    ensure_dotenv_loaded()

    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    if deepseek_key:
        extra_payload: Dict[str, Any] = {}

        if thinking is not None:
            extra_payload["thinking"] = {
                "type": "enabled" if thinking else "disabled",
            }

        return ChatProviderConfig(
            provider="deepseek",
            api_key=deepseek_key,
            chat_url=os.getenv("DEEPSEEK_CHAT_URL", DEEPSEEK_DEFAULT_CHAT_URL),
            model=os.getenv("DEEPSEEK_MODEL", DEEPSEEK_DEFAULT_MODEL),
            extra_payload=extra_payload,
        )

    dashscope_key = os.getenv("DASHSCOPE_API_KEY", "").strip()

    if dashscope_key:
        return ChatProviderConfig(
            provider="dashscope",
            api_key=dashscope_key,
            chat_url=os.getenv("DASHSCOPE_CHAT_URL", DASHSCOPE_DEFAULT_CHAT_URL),
            model=os.getenv("DASHSCOPE_CHAT_MODEL", DASHSCOPE_DEFAULT_MODEL),
        )

    return ChatProviderConfig()


def has_chat_provider() -> bool:
    """
    当前是否配置了可用的大模型供应商。

    替代原代码里散落的 os.getenv("DASHSCOPE_API_KEY") 判断，
    避免换成 DeepSeek 之后这些开关全部失效。
    """
    return resolve_chat_provider().available


def describe_chat_provider() -> str:
    """返回一行供应商说明，用于 Demo 输出。"""
    config = resolve_chat_provider()

    if not config.available:
        return "未配置大模型 API Key，CoT 与 SQL 生成走 Mock"

    return f"provider={config.provider}, model={config.model}"


def use_local_models() -> bool:
    """
    是否启用本地 bge 向量 / 精排模型。

    默认关闭，保持"无配置即 Mock"的行为不变（Demo 秒开、不下载模型）。
    显式打开后，Schema 检索的向量召回与 Rerank 精排换成本地开源模型：
        export ASKDATA_LOCAL_MODELS=1
    """
    ensure_dotenv_loaded()

    flag = os.getenv("ASKDATA_LOCAL_MODELS", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}
