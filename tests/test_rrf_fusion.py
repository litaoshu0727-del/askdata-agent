from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402
from schema_retrieval.rrf_fusion_client import (  # noqa: E402
    RouteRecallResult,
    RRFFusionClient,
    RRFFusionConfig,
)

# E19 的形态：3 个检索词各两路。字段 0 只被"用户浏览行为"命中，两路都排第 1；
# 字段 10~29 是"顺带命中"的——每个词的每一路都排在中游。
TARGET = 0
FILLERS = list(range(10, 30))


def routes():
    result = []
    for term in ("用户浏览行为", "平均停留时长", "秒"):
        for route in ("keyword", "vector"):
            ranked = ([TARGET] if term == "用户浏览行为" else []) + FILLERS
            result.append(RouteRecallResult(route_name=route, query_term=term, ranked_doc_indices=ranked))
    return result


def fuse(per_term_top_k, pool_size=10):
    """池子大小 = min(关键词数 × 6 夹在上下限之间, final_top_k)，这里两个都设成 pool_size。"""
    client = RRFFusionClient(RRFFusionConfig(
        rrf_k=60, truncate_multiplier=6, min_fused_top_k=pool_size, max_fused_top_k=80,
        final_top_k=pool_size, per_term_top_k=per_term_top_k,
    ))
    return client.fuse(route_results=routes(), keyword_count=3)


class PerTermPoolGuaranteeTest(unittest.TestCase):
    def test_single_term_leader_loses_global_rrf(self):
        """不保底时，只被一个词命中的第 1 名进不了池——这就是要修的结构。"""
        pool = [hit.doc_index for hit in fuse(per_term_top_k=0)]
        self.assertNotIn(TARGET, pool)
        self.assertEqual(len(pool), 10)

    def test_single_term_leader_is_guaranteed(self):
        pool = [hit.doc_index for hit in fuse(per_term_top_k=3)]
        self.assertIn(TARGET, pool)

    def test_guarantee_is_added_not_swapped(self):
        """保底名额是追加的：全局排名本来在池里的，一个都不能被挤掉。"""
        without = {hit.doc_index for hit in fuse(per_term_top_k=0)}
        with_guarantee = {hit.doc_index for hit in fuse(per_term_top_k=3)}
        self.assertTrue(without <= with_guarantee)
        self.assertEqual(with_guarantee - without, {TARGET})

    def test_no_duplicates_and_sorted_by_global_score(self):
        hits = fuse(per_term_top_k=3)
        indices = [hit.doc_index for hit in hits]
        self.assertEqual(len(indices), len(set(indices)))
        scores = [hit.score for hit in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_leaders_already_in_pool_add_nothing(self):
        """池子够大、各词的前几名本来就在里面时，保底不改变结果。"""
        big = [hit.doc_index for hit in fuse(per_term_top_k=3, pool_size=40)]
        off = [hit.doc_index for hit in fuse(per_term_top_k=0, pool_size=40)]
        self.assertIn(TARGET, off)
        self.assertEqual(big, off)


    def test_several_guaranteed_fields_are_sorted_among_themselves(self):
        """
        追加的保底字段分数一定不高于池尾，排序只在它们之间起作用：
        先追加的 X（只在两个列表里）要排在后追加、但还多出现一次的 Y 后面。
        """
        x, y = 0, 1
        route_results = []
        for term, leader in (("用户浏览行为", x), ("秒", y)):
            for route in ("keyword", "vector"):
                route_results.append(RouteRecallResult(route, term, [leader] + FILLERS))
        route_results.append(RouteRecallResult("vector", "平均停留时长", FILLERS + [y]))

        client = RRFFusionClient(RRFFusionConfig(
            rrf_k=60, min_fused_top_k=10, max_fused_top_k=80, final_top_k=10, per_term_top_k=3,
        ))
        hits = client.fuse(route_results=route_results, keyword_count=3)
        indices = [hit.doc_index for hit in hits]

        self.assertEqual(indices[-2:], [y, x])


class PipelineConfigTest(unittest.TestCase):
    def test_pipeline_retrieval_configs_keep_the_guarantee_on(self):
        """上面的测试都显式传参；这里锁住主链路实际用的配置，免得有人在那里把它关了。"""
        for dataset in ("trade", "ecommerce", "chinook"):
            with self.subTest(dataset=dataset):
                stub = SimpleNamespace(config=SimpleNamespace(dataset=dataset))
                config = AskDataText2SQLPipeline._build_retrieval_config(stub)
                self.assertEqual(config.rrf_config.per_term_top_k, 3)

if __name__ == "__main__":
    unittest.main()
