"""
上下文 Query 改写（指代消解）。

多轮对话里用户会说"它们的退款金额呢"、"这些店铺的买家数"。
指代对象不在当前 Query 里，只存在于会话记忆中。

原来的做法是把会话记忆拼在 Query 前面一起送进 CoT，指望模型顺手解决。
实测不行，两种失败都会出现：

    关键词抽取拿到的是原始 Query，把"它们"当成了检索词，
    真正的指代对象（店铺名）根本没进检索。

    CoT 看到了上下文，但没被要求先解指代，
    结果要么忽略限定条件查了全表，要么从店铺名"臻品自营店15"里
    抠出数字 15 当成 shop_id，凭空造出一个过滤条件。

所以把指代消解拆成显式的一步：先把追问改写成**自包含**的问题，
再送进后面的关键词抽取和 CoT。这就是检索增强里常说的 query rewriting。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from askdata_diagnostics import Codes, OnceEmitter, emit
from llm_config import resolve_chat_provider
from llm_http import post_json

# 出现这些词才认为可能有指代，避免每轮都白白多调一次模型。
REFERENCE_MARKERS = (
    "它们", "他们", "她们", "它", "这些", "那些", "这几个", "那几个",
    "这个", "那个", "刚才", "上面", "前面", "上述", "该", "其中",
    "同样", "再看", "还有呢", "以上", "回到", "上一轮",
)

# 固定词列不全：第一套多轮题里"这几家""这三个品牌""这3个""浏览最多的那位""那家公司"都没触发改写。
#   这/那 + 数量（可省）+ 量词：这几家、这三个、这3个、那位、那家、这张……
#   省略式追问："2023年同一季度呢？""PG-13 的呢？"
REFERENCE_PATTERNS = (
    re.compile(r"[这那](?:[几两一二三四五六七八九十百\d]+)?[个位家张部首条款种类笔件名只本支批份项单]"),
    re.compile(r"呢\s*(?:[？?，,。]|$)"),
)

# 第 2、4、5、6 条来自第一套多轮题：
#   第 4 条：挑"最多/最高"的那一个，候选和数值都在上下文里，照样挑错：五个分级里挑了 R（1666），最多的是 PG-13（1814）
#     （M1S05-2）；JetBrains 40.62 和 Embraer 39.62 挑了后者（M1C07-4）。不开思考模式，就让它先把每一行抄出来比一遍再写结论。
#   第 2 条：上一轮结果里有商品 ID 30023，改写只写了商品名，库里另一个商品同名，SQL 把两个一起算了（M1E10-3）。
#   第 5 条："小程序的呢？"照搬了第 1 轮的问法，丢了上一轮的"按年龄段拆开"（M1E11-3）。
#   第 4 条后半、第 6 条是拿真实会话回放新提示词时发现的：上一轮只查了最少的那一个，问倒数第二，改写自己补了一句
#     "Purchased AAC 之外第二少"，其实是倒数第三（M1C08-4）；把上一轮的笔数写进了改写（M1S06-2）。
# 第 8、9 条来自两套多轮题的同一种错：改写丢了"不管有没有完成都算"，又写成"……的退款中，旗舰店……"，这个"中"是
#   "在这些退款里"，规划和过滤检查都当成了状态取值，只算了退款中的（M1E05-3、M2E05-4）。
REWRITE_PROMPT = """你是一个对话式数据查询系统的 Query 改写模块。

任务：根据会话历史，把用户当前这句话改写成一个**自包含**的查询问题。

要求：
1. 把所有指代词（它们、这些、刚才那几个……）替换成会话历史中对应的具体对象。
2. 指代对象要用历史结果里出现过的**原始值**，例如店铺名称就用店铺名称原文。历史结果里有这些对象的 ID 列，就把 ID 一起写上，例如"商品 30023（都乐 海南芒果 3斤）"——名称可能重名，ID 不会。没有 ID 列就只写名称。
3. ID 只能照抄历史结果里 ID 列的值，绝对不要凭空推断。比如店铺名叫"臻品自营店15"，不代表它的 ID 是 15。
4. 要按历史结果里的数值挑对象时（最多、最高、最少、最低、排第一……），先在"依据"里把每一行的对象和数值逐个抄出来、比出大小，再改写。以下情况不要挑，保留用户原来的说法，写明是哪一轮的什么结果，也不要自己解释排名：历史结果没有列全（写着"只列出前几行"或以"……"结尾）；历史结果里没有可比的那些数值（比如上一轮只查了第一名，用户问倒数第二）。
5. 省略式追问（"小程序的呢？""PG-13 的呢？"）沿用被省略的那一轮的完整问法：一般是最近一轮；用户点明了"也按一级类目看"这类说法，就找对应的那一轮。指标、拆分维度、筛选条件照搬，只换掉用户这次说的部分。
6. 改写里不要写历史结果里的统计数值（笔数、金额、销量……）：那是上一轮的答案，不是这一轮的条件。
7. 只补充指代信息，不要改变用户的查询意图，不要添加历史里没有的筛选条件。
8. 沿用前面某一轮的范围时，用户当时说的口径说明（"不管有没有完成都算""取消的也算"这类）一起带上，不能丢。
9. 说"在这些记录里"时用"里"，不用"中"：写"质量问题的退款里，旗舰店……"，不写"质量问题的退款中，旗舰店……"。"退款中""审核中"这样的词可能是状态取值，会被当成筛选条件。用户点名这个状态时照常写。
10. 如果当前问题本身已经自包含，原样返回。

只输出两行，不要别的：
依据：第 4 条写比较过程，第 5 条写沿用的是哪一轮、照搬了什么；其余情况写"无"
改写：改写后的问题

会话历史：
{context}

用户当前问题：{query}
"""

# 依据那一行可能写好几行，取最后一个行首的"改写："。
REWRITE_LINE = re.compile(r"^\s*改写\s*[：:]", re.M)
# 会话记忆里的段落标题，去掉标题之后什么都不剩，就是没有历史。
SECTION_HEADER = re.compile(r"^\[[^\]\n]+\]$", re.M)


@dataclass
class RewriteResult:
    """改写结果。"""

    original: str
    rewritten: str
    changed: bool = False
    skipped_reason: str = ""
    basis: str = ""

    @property
    def effective(self) -> str:
        """后续环节应该使用的 Query。"""
        return self.rewritten or self.original


@dataclass
class QueryRewriterConfig:
    """改写器配置。"""

    api_key: str = ""
    chat_url: str = ""
    model: str = ""
    timeout: int = 60
    # 只防窗口之外的调用方传进超长文本。会话记忆窗口才是真正的上限（网页和评测都是最多 8 条消息、约 4000 token）。
    # 原来是 2000 字，从头截：第 4 轮回到第 1 轮时，第 1 轮的回答被截掉一半，改写只写进了剩下的几张发票（M1C06-4）。
    max_context_chars: int = 16000
    extra_payload: Dict[str, Any] = field(default_factory=dict)


class ContextualQueryRewriter:
    """
    把带指代的追问改写成自包含 Query。

    没有 API Key 时原样返回并上报一次降级——多轮追问在这种情况下
    本来就不可能正确工作，不该让它悄悄退化成"查全表"。
    """

    def __init__(self, config: Optional[QueryRewriterConfig] = None):
        self.config = config or QueryRewriterConfig()

        # 改写要的是忠实转述，不是发散推理，DeepSeek 下关闭思考模式。
        provider = resolve_chat_provider(thinking=False)

        if not self.config.api_key:
            self.config.api_key = provider.api_key

        if not self.config.chat_url:
            self.config.chat_url = provider.chat_url

        if not self.config.model:
            self.config.model = provider.model

        if not self.config.extra_payload:
            self.config.extra_payload = dict(provider.extra_payload)

        self._degrade = OnceEmitter()

    @staticmethod
    def looks_contextual(query: str) -> bool:
        """当前 Query 里是否出现了疑似指代词。"""
        return any(marker in query for marker in REFERENCE_MARKERS) or any(
            pattern.search(query) for pattern in REFERENCE_PATTERNS
        )

    def rewrite(self, query: str, conversation_context: str) -> RewriteResult:
        """
        改写当前 Query。

        Args:
            query: 用户原始问题。
            conversation_context: 会话记忆文本。

        Returns:
            RewriteResult: 改写结果，失败时回退为原 Query。
        """
        context = self._drop_current_question(conversation_context.strip(), query)
        if not SECTION_HEADER.sub("", context).strip():
            return RewriteResult(original=query, rewritten=query, skipped_reason="无会话上下文")

        if not self.looks_contextual(query):
            return RewriteResult(original=query, rewritten=query, skipped_reason="未检测到指代词")

        if not self.config.api_key:
            self._degrade.emit(
                Codes.QUERY_REWRITE_SKIPPED,
                "检测到指代词但未配置 API Key，无法做指代消解，"
                "本轮会按字面查询，多轮追问结果大概率不正确",
                原问题=query,
            )
            return RewriteResult(original=query, rewritten=query, skipped_reason="无 API Key")

        if len(context) > self.config.max_context_chars:
            context = context[-self.config.max_context_chars:]

        try:
            reply = self._call_model(
                REWRITE_PROMPT.format(context=context, query=query)
            )
        except Exception as exc:
            emit(
                Codes.QUERY_REWRITE_FAILED,
                "指代消解调用失败，回退为原始 Query，本轮多轮追问可能不正确",
                原因=str(exc)[:80],
            )
            return RewriteResult(original=query, rewritten=query, skipped_reason="调用失败")

        basis, rewritten = self._split_reply(reply)
        rewritten = rewritten.strip().strip('"').strip("“”").strip()

        if not rewritten:
            return RewriteResult(original=query, rewritten=query, skipped_reason="模型返回为空")

        return RewriteResult(
            original=query,
            rewritten=rewritten,
            changed=rewritten != query,
            basis=basis,
        )

    @staticmethod
    def _drop_current_question(context: str, query: str) -> str:
        """
        会话记忆在查询之前就记下了这一轮的提问，历史里最近那条用户消息就是当前问题，去掉。

        留着它，模型看到"历史里已经有这句话"就当它自包含、原样返回：
        "标价4.99的那些里，被租次数最多的5部"3 次都没改写，丢了上一轮的 NC-17（M1S08-3）。
        """
        line = f"用户：{query.strip()}"
        index = context.rfind(line)
        if index < 0 or "\n助手：" in context[index:]:
            return context
        return (context[:index].rstrip() + context[index + len(line):]).strip()

    @staticmethod
    def _split_reply(reply: str) -> Tuple[str, str]:
        """拆出依据和改写后的问题；没按两行格式写时，整段当作改写结果。"""
        markers = list(REWRITE_LINE.finditer(reply))
        if not markers:
            return "", reply
        basis = reply[: markers[-1].start()].strip()
        basis = re.sub(r"^依据\s*[：:]\s*", "", basis)
        lines = [line.strip() for line in reply[markers[-1].end():].splitlines() if line.strip()]
        return basis, lines[0] if lines else ""

    def _call_model(self, prompt: str) -> str:
        """调用 Chat Completions 接口。"""
        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "stream": False,
        }
        payload.update(self.config.extra_payload)

        result = post_json(self.config.chat_url, payload, self.config.api_key, self.config.timeout, label="指代消解模型")

        return result["choices"][0]["message"]["content"]
