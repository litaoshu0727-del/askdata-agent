from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型，不加载本地大模型。
# 必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in (
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_WORKSPACE_ID",
    "ASKDATA_LOCAL_MODELS",
):
    os.environ.pop(_key, None)

# 降级告警在测试里是预期行为，不需要刷到 stderr；断言仍然基于 collect() 的结果。
import logging  # noqa: E402

logging.getLogger("askdata").disabled = True

import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_diagnostics import Codes, collect, silenced  # noqa: E402
from askdata_pipeline.data_qa import build_metric_glossary  # noqa: E402
from askdata_pipeline.ecommerce_data import get_ecommerce_business_meta  # noqa: E402
from askdata_pipeline.query_rewriter import (  # noqa: E402
    ContextualQueryRewriter,
    QueryRewriterConfig,
)

CONTEXT = '[近期对话] 用户：销售额最高的三个店铺是哪些 助手：查询结果：臻品自营店15、优选旗舰店1、旗舰旗舰店7'


class ReferenceDetectionTestCase(unittest.TestCase):
    """指代词检测：决定要不要多花一次模型调用。"""

    def test_detects_common_reference_words(self):
        for query in [
            "它们的退款金额分别是多少",
            "这些店铺的买家数",
            "刚才第一名叫什么",
            "上述店铺的转化率",
            "其中哪家最高",
            # 第一套多轮题里原来没触发改写的说法
            "这几家各退了多少钱？",
            "这三个品牌的商品5月被加购了多少次？",
            "这3个5月卖出去多少件？",
            "浏览最多的那位，收藏过哪些商品？",
            "消费最高的那家公司，买过哪些流派的曲目？",
            "2023年同一季度呢？",
            "回到那三张专辑，它们的曲目平均每首多长？",
        ]:
            with self.subTest(问题=query):
                self.assertTrue(ContextualQueryRewriter.looks_contextual(query))

    def test_self_contained_query_needs_no_rewrite(self):
        for query in [
            "销售额最高的三个店铺是哪些",
            "客单价最高的10个用户是谁",
            "因为商品质量问题退款的总金额是多少",
        ]:
            with self.subTest(问题=query):
                self.assertFalse(ContextualQueryRewriter.looks_contextual(query))


class RewriteSkipTestCase(unittest.TestCase):
    """不该调模型的几种情况，必须短路返回。"""

    def setUp(self):
        self.rewriter = ContextualQueryRewriter(QueryRewriterConfig(api_key=""))

    def test_no_context_skips(self):
        result = self.rewriter.rewrite("它们的退款金额呢", "")

        self.assertFalse(result.changed)
        self.assertEqual(result.effective, "它们的退款金额呢")
        self.assertEqual(result.skipped_reason, "无会话上下文")

    def test_no_reference_word_skips_without_calling_model(self):
        """自包含的问题不该浪费一次模型调用。"""
        result = self.rewriter.rewrite("销售额最高的三个店铺是哪些", CONTEXT)

        self.assertFalse(result.changed)
        self.assertEqual(result.skipped_reason, "未检测到指代词")

    def test_first_turn_has_no_history(self):
        """会话记忆先记下提问再查询：第一轮的"历史"里只有当前这一句，等于没有历史。"""
        result = self.rewriter.rewrite("这个月的销售额是多少", "[近期对话]\n用户：这个月的销售额是多少")

        self.assertFalse(result.changed)
        self.assertEqual(result.skipped_reason, "无会话上下文")

    def test_missing_api_key_emits_diagnostic(self):
        """
        有指代词却没有 Key，是"多轮追问必定不正确"的状态，
        不能安静地退化成按字面查询。
        """
        with silenced(), collect() as diagnostics:
            result = self.rewriter.rewrite("它们的退款金额呢", CONTEXT)

        self.assertFalse(result.changed)
        self.assertEqual(result.effective, "它们的退款金额呢")
        self.assertIn(
            Codes.QUERY_REWRITE_SKIPPED,
            {item.code for item in diagnostics},
        )


class RewriteWithStubModelTestCase(unittest.TestCase):
    """接一个假模型，验证改写结果被正确清洗和传递。"""

    def _rewriter(self, reply: str) -> ContextualQueryRewriter:
        rewriter = ContextualQueryRewriter(
            QueryRewriterConfig(
                api_key="sk-stub",
                chat_url="https://example.invalid/chat",
                model="stub",
            )
        )
        rewriter._call_model = lambda prompt: reply
        return rewriter

    def test_prompt_keeps_scope_notes_and_avoids_status_like_words(self):
        """M1E05-3、M2E05-4：改写丢了"都算"，又把"在这些退款里"写成"退款中"，被当成状态取值。"""
        seen = []
        rewriter = self._rewriter("改写：无")
        rewriter._call_model = lambda prompt: seen.append(prompt) or "改写：无"
        rewriter.rewrite("它们的退款金额呢", CONTEXT)

        self.assertIn("口径说明", seen[0])
        self.assertIn('用"里"，不用"中"', seen[0])

    def test_rewrite_replaces_reference(self):
        rewriter = self._rewriter("臻品自营店15、优选旗舰店1、旗舰旗舰店7的退款金额分别是多少")
        result = rewriter.rewrite("它们的退款金额分别是多少", CONTEXT)

        self.assertTrue(result.changed)
        self.assertIn("臻品自营店15", result.effective)
        self.assertNotIn("它们", result.effective)

    def test_quotes_are_stripped(self):
        rewriter = self._rewriter('"臻品自营店15的退款金额是多少"')
        result = rewriter.rewrite("它的退款金额是多少", CONTEXT)

        self.assertFalse(result.effective.startswith('"'))

    def test_basis_line_is_split_off(self):
        """先写依据再写改写：只有"改写："后面那句往下传，依据留着排查用。"""
        rewriter = self._rewriter(
            "依据：G 1442、NC-17 1599、PG 1600、PG-13 1814、R 1666，\n最多的是 PG-13（1814）\n"
            "改写：PG-13 分级的影片，按租出的门店拆开看看逾期笔数。"
        )
        result = rewriter.rewrite("逾期最多的那个分级，按租出的门店拆开看看。", CONTEXT)

        self.assertEqual(result.effective, "PG-13 分级的影片，按租出的门店拆开看看逾期笔数。")
        self.assertTrue(result.basis.startswith("G 1442"))
        self.assertIn("最多的是 PG-13", result.basis)

    def test_reply_without_format_is_taken_whole(self):
        rewriter = self._rewriter("臻品自营店15的退款金额是多少")
        result = rewriter.rewrite("它的退款金额是多少", CONTEXT)

        self.assertEqual(result.effective, "臻品自营店15的退款金额是多少")
        self.assertEqual(result.basis, "")

    def test_current_question_is_not_in_history(self):
        """
        会话记忆里最近那条用户消息就是当前问题。留着它，新提示词下模型当它自包含、原样返回（M1S08-3）。
        """
        prompts = []
        rewriter = self._rewriter("")
        rewriter._call_model = lambda prompt: prompts.append(prompt) or "改写：NC-17 分级、标价 4.99 的影片里，被租次数最多的5部"
        query = "标价4.99的那些里，被租次数最多的5部是哪些？"
        context = (
            "[近期对话]\n用户：NC-17 的那些，按租借标价拆开看看\n助手：查询结果：0.99、2.99、4.99\n"
            f"用户：{query}\n[个人知识库召回]\n1. 常看 NC-17 影片"
        )

        rewriter.rewrite(query, context)

        history = prompts[0].split("会话历史：")[1].split("用户当前问题：")[0]
        self.assertNotIn(query, history)
        self.assertIn("用户：NC-17 的那些", history)
        self.assertIn("[个人知识库召回]", history)

    def test_same_question_asked_before_stays_in_history(self):
        """同一句话前面问过、已经有回答的，是历史，不能删。"""
        prompts = []
        rewriter = self._rewriter("")
        rewriter._call_model = lambda prompt: prompts.append(prompt) or "改写：臻品自营店15的退款金额"
        context = "[近期对话]\n用户：它们的退款金额呢\n助手：查询结果：100\n用户：它们的退款金额呢"

        rewriter.rewrite("它们的退款金额呢", context)

        history = prompts[0].split("会话历史：")[1].split("用户当前问题：")[0]
        self.assertIn("用户：它们的退款金额呢\n助手：查询结果：100", history)
        self.assertEqual(history.count("它们的退款金额呢"), 1)

    def test_earlier_turns_reach_the_model(self):
        """
        原来只给模型最后 2000 字：第 4 轮回到第 1 轮时，第 1 轮的回答被截掉一半（M1C06-4）。
        记忆窗口才是上限，窗口里的内容要原样给到。
        """
        prompts = []
        rewriter = self._rewriter("回到 InvoiceId 292、298、299、306、311 这几张发票")
        rewriter._call_model = lambda prompt: prompts.append(prompt) or "改写后的问题"
        first_answer = "助手：查询结果：" + "、".join(str(292 + i) for i in range(200))
        context = "[近期对话]\n用户：2024年第三季度金额超过10的发票\n" + first_answer + "\n" + "用户：后面几轮\n" * 300

        rewriter.rewrite("回到2024年那几张发票", context)

        self.assertGreater(len(context), 2000)
        self.assertIn(first_answer, prompts[0])

    def test_model_failure_falls_back_to_original(self):
        rewriter = ContextualQueryRewriter(
            QueryRewriterConfig(api_key="sk-stub", chat_url="x", model="stub")
        )

        def boom(prompt):
            raise RuntimeError("网络炸了")

        rewriter._call_model = boom

        with silenced(), collect() as diagnostics:
            result = rewriter.rewrite("它们的退款金额呢", CONTEXT)

        self.assertEqual(result.effective, "它们的退款金额呢")
        self.assertIn(
            Codes.QUERY_REWRITE_FAILED,
            {item.code for item in diagnostics},
        )


class MetricGlossaryTestCase(unittest.TestCase):
    """
    指标口径表。

    "客单价怎么算的"曾经答不出来，因为 data_qa 只拿得到会话记忆、看不到 Schema。
    """

    def setUp(self):
        self.glossary = build_metric_glossary(get_ecommerce_business_meta())

    def test_glossary_maps_business_term_to_column(self):
        self.assertIn("客单价", self.glossary)
        self.assertIn("dws_user_summary.avg_order_amount", self.glossary)

    def test_glossary_covers_ambiguous_amount_fields(self):
        for fragment in [
            "dws_shop_daily.gmv",
            "fact_order.pay_amount",
            "fact_refund.refund_amount",
        ]:
            with self.subTest(字段=fragment):
                self.assertIn(fragment, self.glossary)

    def test_empty_meta_returns_empty_glossary(self):
        self.assertEqual(build_metric_glossary(None), "")
        self.assertEqual(build_metric_glossary({}), "")

    def test_glossary_is_truncated(self):
        glossary = build_metric_glossary(get_ecommerce_business_meta(), max_chars=200)

        self.assertLessEqual(len(glossary), 260)
        self.assertIn("已截断", glossary)


if __name__ == "__main__":
    unittest.main()
