from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class RRFFusionConfig:
    """RRF 融合配置，用于控制候选融合和截断策略。"""

    rrf_k: int = 60  # RRF 平滑参数，越大排名差异越平滑
    truncate_multiplier: int = 6  # 根据关键词数量扩展融合候选数
    min_fused_top_k: int = 10  # 融合候选数量下限
    max_fused_top_k: int = 50  # 融合候选数量上限
    final_top_k: int = 8  # 最终输出候选数量
    per_term_top_k: int = 3
    """
    每个检索词保底进候选池的名额：只融合这个词自己的几路召回，前 N 名一定进池。

    全局 RRF 把各个词的得分加在一起。大库上每路召回取前 30 名，81 个字段一路就取走
    三分之一以上，rrf_k=60 又把名次差距抹得很平（第 1 名 1/61，第 30 名 1/90），
    总分实际上成了"出现在几个列表里"：只被一个词命中的字段，哪怕在这个词的两路里
    都排第 1，也抢不过被几个词顺带命中的字段。

    E19「用户浏览行为、平均停留时长、秒」：behavior_type 在"用户浏览行为"下排第 1，
    只出现在 6 个列表里的 2 个，全局排第 21，池子 20 个——进不了池，后面的精排和
    补回都碰不到它。主题库和留出集三 126 次运行、248 个必中字段里，12 个没进池，
    其中 10 个在自己那个词下排前 3。

    名额是追加的，不挤占全局排名的位置。0 表示关闭。
    取 3 和 keyword_coverage_top_k 同一个口径："一个词的前 3 个强命中"。
    """

    route_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "keyword": 1.0,
            "vector": 1.0,
        }
    )  # 不同召回通道的融合权重


@dataclass
class RouteRecallResult:
    """单个召回通道在某个检索词下的召回结果。"""

    route_name: str  # 召回通道名称，如 keyword、vector
    query_term: str  # 当前召回使用的检索词
    ranked_doc_indices: List[int]  # 按相关性排序的文档下标


@dataclass
class RRFFusionHit:
    """RRF 融合后的候选字段结果。"""

    doc_index: int  # 字段文档下标
    score: float  # RRF 融合得分
    matched_terms: List[str]  # 命中的检索词
    sources: List[str]  # 命中的召回通道
    best_rank_by_source: Dict[str, int]  # 各召回通道中的最好排名


class RRFFusionClient:
    """RRF 融合客户端，用于融合关键词召回和向量召回结果。"""

    def __init__(self, config: Optional[RRFFusionConfig] = None):
        self.config = config or RRFFusionConfig()

    def fuse(
        self,
        route_results: List[RouteRecallResult],
        keyword_count: int,
        final_top_k: Optional[int] = None,
    ) -> List[RRFFusionHit]:
        """对多个召回通道的结果进行 RRF 融合排序。"""
        fused_scores: Dict[int, float] = {}
        term_scores: Dict[str, Dict[int, float]] = {}
        matched_terms_map: Dict[int, Set[str]] = {}
        sources_map: Dict[int, Set[str]] = {}
        best_rank_by_source_map: Dict[int, Dict[str, int]] = {}

        for route_result in route_results:
            route_name = route_result.route_name
            query_term = route_result.query_term
            route_weight = self.config.route_weights.get(route_name, 1.0)

            for rank, doc_index in enumerate(route_result.ranked_doc_indices, start=1):
                score_delta = route_weight / (self.config.rrf_k + rank)

                fused_scores[doc_index] = fused_scores.get(doc_index, 0.0) + score_delta
                per_term = term_scores.setdefault(query_term, {})
                per_term[doc_index] = per_term.get(doc_index, 0.0) + score_delta

                matched_terms_map.setdefault(doc_index, set()).add(query_term)
                sources_map.setdefault(doc_index, set()).add(route_name)

                source_rank_map = best_rank_by_source_map.setdefault(doc_index, {})

                if route_name not in source_rank_map:
                    source_rank_map[route_name] = rank
                else:
                    source_rank_map[route_name] = min(source_rank_map[route_name], rank)

        fused_top_k = self.calculate_fused_top_k(keyword_count)

        sorted_items = sorted(
            fused_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        truncated_items = sorted_items[:fused_top_k]

        output_top_k = final_top_k or self.config.final_top_k
        final_items = truncated_items[:output_top_k]

        # 每个检索词自己的前 N 名保底进池，追加在全局排名之外
        selected = {doc_index for doc_index, _ in final_items}
        for doc_index in self._term_leaders(term_scores):
            if doc_index not in selected:
                final_items.append((doc_index, fused_scores[doc_index]))
                selected.add(doc_index)

        final_items.sort(key=lambda item: item[1], reverse=True)

        return [
            RRFFusionHit(
                doc_index=doc_index,
                score=score,
                matched_terms=sorted(matched_terms_map.get(doc_index, set())),
                sources=sorted(sources_map.get(doc_index, set())),
                best_rank_by_source=best_rank_by_source_map.get(doc_index, {}),
            )
            for doc_index, score in final_items
        ]

    def _term_leaders(self, term_scores: Dict[str, Dict[int, float]]) -> List[int]:
        """每个检索词只看自己那几路召回的融合排名，取前 per_term_top_k 名。"""
        top_k = self.config.per_term_top_k

        if top_k <= 0:
            return []

        leaders: List[int] = []

        for scores in term_scores.values():
            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            leaders.extend(doc_index for doc_index, _ in ranked[:top_k])

        return leaders

    def term_rankings(self, route_results: List[RouteRecallResult]) -> Dict[str, List[int]]:
        """每个检索词只融合自己那几路召回，返回它自己的排名（文档下标，从高到低）。"""
        term_scores: Dict[str, Dict[int, float]] = {}

        for route_result in route_results:
            route_weight = self.config.route_weights.get(route_result.route_name, 1.0)
            scores = term_scores.setdefault(route_result.query_term, {})

            for rank, doc_index in enumerate(route_result.ranked_doc_indices, start=1):
                scores[doc_index] = scores.get(doc_index, 0.0) + route_weight / (self.config.rrf_k + rank)

        return {
            term: [doc_index for doc_index, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]
            for term, scores in term_scores.items()
        }

    def calculate_fused_top_k(self, keyword_count: int) -> int:
        """根据关键词数量动态计算融合候选截断数量。"""
        dynamic_top_k = keyword_count * self.config.truncate_multiplier

        return max(
            self.config.min_fused_top_k,
            min(dynamic_top_k, self.config.max_fused_top_k),
        )