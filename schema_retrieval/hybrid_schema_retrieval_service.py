from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

import numpy as np

from askdata_diagnostics import Codes, emit
from schema_retrieval.bm25 import BM25Index
from schema_retrieval.embedding_client import (
    AliyunEmbeddingClient,
    AliyunEmbeddingConfig,
)
from schema_retrieval.graph_builder import build_schema_graph
from schema_retrieval.keyword_extractor_client import (
    AliyunKeywordExtractor,
    AliyunKeywordExtractorConfig,
)
from schema_retrieval.objects import SchemaHit
from schema_retrieval.rerank_client import (
    AliyunRerankClient,
    AliyunRerankConfig,
    RerankDocument,
    RerankResult,
)
from schema_retrieval.rrf_fusion_client import (
    RRFFusionClient,
    RRFFusionConfig,
    RRFFusionHit,
    RouteRecallResult,
)
from schema_retrieval.sqlite_loader import SQLiteSchemaLoader
from schema_retrieval.vector_index import VectorIndex


@dataclass
class HybridFieldDocument:
    """
    混合检索字段文档。

    一个字段会同时维护三类文本：
    - keyword_text：用于 BM25 关键词召回
    - vector_text：用于 Embedding 向量召回
    - rerank_text：用于 Rerank 精排
    """

    doc_id: str
    column: object
    keyword_text: str
    vector_text: str
    rerank_text: str


@dataclass
class HybridSchemaRetrievalConfig:
    """
    混合 Schema 检索服务配置。
    """

    per_keyword_top_k: int = 20
    """每个关键词在每一路召回中的 Top-K 数量。"""

    include_join_columns: bool = True

    dominant_keyword_ratio: float = 3.0
    """
    字面命中"压倒性"的判定倍数。

    某个字段在 BM25 里排第一、且分数达到第二名的这个倍数时，
    直接保送进最终结果，不参与精排淘汰。

    动机：RRF 只看排名不看分数。"直播间"在 fact_order.channel 上得 27.1 分，
    第二名只有 3.5 分——7.7 倍的压倒性证据，在 RRF 里却和"向量路第一名"
    贡献同样的 1/(60+k)，强度信息被完全抹掉，随后被精排按语义相关度淘汰。

    设成 0 可关闭该机制。
    """

    dominant_keyword_min_score: float = 8.0
    """保送的绝对分数下限，避免在整体分数都很低时误保送。"""

    keyword_coverage_top_k: int = 3
    """
    覆盖判据：一个关键词的前 K 个**同级**强命中里，如果一个都没进最终结果，
    就把它的第一名补回来。0 表示关闭这条判据。

    "同级"由 dominant_keyword_tie_ratio 界定，这是这条判据的关键——
    见下面 E51 的例子。K 只是个上限，真正起作用的是同级这个条件。

    断层判据有个盲区——**第二名往往是第一名的同义近邻**。实测 E24
    「北京用户一共下了多少笔订单」，BM25 在 dim_user.city 上打 17.52 分、
    在 dim_user.province 上打 16.08 分，比值 1.09：两个字段的索引文本
    高度重合，分数天然咬得死紧，谁也甩不开谁 3 倍，于是谁都不算压倒性。
    没有元数据时更极端，dim_user.city 和 dim_shop.city 同为 10.55 分，
    比值正好 1.00。

    断层判据问的是"这个词是不是只可能指这一个字段"，覆盖判据问的是另一件事：
    **"这个词有没有人替它说话"**。两者互补——

        断层    精度导向，某个字段证据压倒性，别让精排淘汰它
        覆盖    召回导向，某个检索意图一个代表都没有，至少给它留一个位置

    E24「北京用户一共下了多少笔订单」就是后者：『北京用户』的前三名
    （dim_user.city / province / dim_shop.city）一个都没进最终结果，
    12 个名额全被另一个关键词『订单笔数』带来的 dws 汇总层字段占满了。

    **判据的关键是"代表必须同级"。**两个实测教训：

    其一，『北京用户』的完整召回集里还有 fact_order.user_id（7.92 分），
    而它恰好进了最终集——按"召回集有任意交集就算有代表"来判，E24 反而不触发。
    召回集每路 20 个、彼此重叠严重，只有前几名才代表这个词真正指向什么。

    其二，E51『已完成订单』的第一名 fact_order.order_status 打 22.01 分却没入选，
    入选的是 fact_order.finish_time（10.09，不到一半）。要是把它算作代表，
    这个词同样被判定为"有人说话了"——而模型接下来干的正是拿
    finish_time IS NOT NULL 去凑"已完成"，算出 59436.98（参考 44149.54），
    降级记录一条都没有。沾边的近义字段不是代表，只有同级的才是。
    """

    dominant_keyword_tie_expand: bool = True
    """
    补回第一名时，是否把同表并列的近邻一起带上。

    分不清"北京"说的是 city 还是 province，两个都给，比赌一个错一个好——
    代价只是 SchemaGraph 多一列。并列的判定见 dominant_keyword_tie_ratio。
    """

    dominant_keyword_tie_ratio: float = 0.85
    """
    并列阈值：分数在第一名这个比例之上的字段，视为同一概念的近邻，一起保送。

    既然分不清"北京"指的是 city 还是 province，两个都给模型，
    比赌一个、错一个好——代价只是 SchemaGraph 多一列。

    断层触发时这条不起作用：真断层意味着第二名远在 0.85 倍之下，
    保送集自然只有第一名，行为与改动前一致。
    """

    max_dominant_per_query: int = 4
    """单次查询最多保送几个字段，防止保送集喧宾夺主。"""

    time_field_guard: bool = True
    """
    时间约束保底：问题里有明确的时间约束（某年、某月、某日、季度、上下旬……）时，
    从数据覆盖了所提年份的时间字段里，用精排挑最贴题的一个，不在结果里就补回。

    精排按"这个字段和整个问题有多相关"打分，而时间是约束不是主题。
    HB16（按流派比较 2023、2024 两年的销售额）里，Track.Bytes 打 0.65，
    InvoiceDate 只有 0.019，排在 60 个候选的第 41——给时间字段的精排文本
    补多少内容都救不回来。

    靠"关键词覆盖"也兜不住：BM25 把「2024年」切成「2024」和「年」，
    Employee.BirthDate 凭"年龄"里的「年」字和 InvoiceDate 打成平手（10.23 比 10.12），
    覆盖规则认的第一名是出生日期。按数据覆盖筛就干净了：BirthDate 覆盖
    1947–1973 年，问 2024 年时根本不在候选里。

    覆盖年份取自 sqlite_loader 从数据算出的 value_range（"2021-01-01 至 2025-12-22，…"）。
    问题里没提年份，或没有字段覆盖所提年份时，所有时间字段都参与挑选。
    """

    include_label_columns: bool = True
    """
    是否自动把每张命中表的名称列补进 SchemaGraph。

    检索偏向指标字段，"哪家店/哪个用户"隐含要的名称列经常被挤掉，
    导致模型只能输出 ID。这个开关按表补齐，代价是每张表多一列。
    """
    """构建 SchemaGraph 时是否自动补充 Join 字段。"""

    rrf_config: RRFFusionConfig = field(
        default_factory=lambda: RRFFusionConfig(
            rrf_k=60,
            truncate_multiplier=6,
            min_fused_top_k=10,
            max_fused_top_k=50,
            final_top_k=20,
            route_weights={
                "keyword": 1.0,
                "vector": 1.0,
            },
        )
    )
    """RRF 融合配置。"""

    rerank_top_multiplier: int = 2
    """
    Rerank 输出数量倍数。

    计算方式：
        rerank_top_n = 关键词数量 * rerank_top_multiplier
    """

    rerank_min_top_n: int = 2
    """Rerank 输出数量下限。"""

    rerank_max_top_n: int = 20

    recall_cap_warn_ratio: float = 0.25
    """精排名额低于候选数的这个比例时告警。"""

    recall_cap_warn_min_candidates: int = 10
    """候选数少于这个值时不告警，小库上截断是正常的。"""
    """Rerank 输出数量上限。"""


@dataclass
class HybridSchemaRetrievalResult:
    """
    混合 Schema 检索服务返回结果。
    """

    query: str
    keywords: List[str]
    route_results: List[RouteRecallResult]
    fusion_hits: List[RRFFusionHit]
    rerank_results: List[RerankResult]
    schema_hits: List[SchemaHit]
    schema_graph: object


class HybridSchemaRetrievalService:
    """
    混合 Schema 检索服务。

    完整流程：
    1. 用户 Query
    2. LLM 抽取关键词
    3. BM25 关键词召回
    4. Embedding 向量召回
    5. RRF 融合
    6. Rerank 精排
    7. SchemaHit
    8. SchemaGraph
    """

    def __init__(
        self,
        tables: dict,
        columns: list,
        relations: list,
        business_meta: Optional[dict],
        embedding_client: AliyunEmbeddingClient,
        rerank_client: AliyunRerankClient,
        keyword_extractor: Optional[AliyunKeywordExtractor] = None,
        config: Optional[HybridSchemaRetrievalConfig] = None,
    ):
        self.tables = tables
        self.columns = columns
        self.relations = relations
        self.business_meta = business_meta or {}
        self.embedding_client = embedding_client
        self.rerank_client = rerank_client
        self.keyword_extractor = keyword_extractor
        self.config = config or HybridSchemaRetrievalConfig()

        self.documents: List[HybridFieldDocument] = []
        self.keyword_index: Optional[BM25Index] = None
        self.vector_index: Optional[VectorIndex] = None
        self.rrf_client = RRFFusionClient(self.config.rrf_config)

        self._enrich_columns_with_business_meta()
        self._build_documents()
        self._build_indices()

    @classmethod
    def from_sqlite(
        cls,
        db_path,
        database_name: str,
        business_meta: Optional[dict],
        embedding_client: AliyunEmbeddingClient,
        rerank_client: AliyunRerankClient,
        keyword_extractor: Optional[AliyunKeywordExtractor] = None,
        config: Optional[HybridSchemaRetrievalConfig] = None,
        sample_size: int = 5,
    ) -> "HybridSchemaRetrievalService":
        """
        从 SQLite 数据库初始化混合 Schema 检索服务。

        Args:
            db_path: SQLite 数据库路径。
            database_name: 数据库名称。
            business_meta: 表级和字段级业务元数据。
            embedding_client: Embedding Client。
            rerank_client: Rerank Client。
            keyword_extractor: 关键词抽取 Client。不传时需要在 retrieve() 中手动传 keywords。
            config: 服务配置。
            sample_size: 字段样例值抽取数量。

        Returns:
            HybridSchemaRetrievalService: 初始化完成的服务实例。
        """
        loader = SQLiteSchemaLoader(
            db_path=db_path,
            database_name=database_name,
            business_meta=business_meta or {},
            sample_size=sample_size,
        )

        tables, columns, relations = loader.load()

        return cls(
            tables=tables,
            columns=columns,
            relations=relations,
            business_meta=business_meta,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
            keyword_extractor=keyword_extractor,
            config=config,
        )

    @classmethod
    def from_milvus(
        cls,
        uri: str,
        embedding_client,
        rerank_client,
        field_collection: str = "schema_field_index_demo",
        relation_collection: str = "schema_relation_index_demo",
        token: str = "",
        keyword_extractor=None,
        config: Optional["HybridSchemaRetrievalConfig"] = None,
    ) -> "HybridSchemaRetrievalService":
        """
        从已构建的 Milvus 索引加载检索服务，不再扫描源库。

        这是 schema_indexing 模块存在的意义：索引一次，多处加载。
        索引里存了完整的 ColumnSchema 与 TableSchema 序列化载荷，
        因此还原出来的 SchemaGraph 与直接扫库完全一致——
        只存检索用的几个标量字段是不够的，那样提示词里的业务语义会整段丢失。

        注意：当前 Demo 规模（11 表 81 字段）下这条路径不带来性能收益。
        扫库加编码只要 0.36 秒，而两个 bge 模型加载要 15 秒，后者省不掉。
        它的价值在规模和解耦：字段涨到几千个时编码开销才显著，
        以及多个查询进程共享同一份索引，而不是各建各的。
        """
        from schema_indexing.milvus_client import (
            MilvusSchemaIndexClient,
            MilvusSchemaIndexConfig,
        )

        index_client = MilvusSchemaIndexClient(
            MilvusSchemaIndexConfig(
                uri=uri,
                token=token,
                field_collection_name=field_collection,
                relation_collection_name=relation_collection,
                recreate_collection=False,
            )
        )

        documents, embeddings, tables = index_client.load_all_fields()

        if not documents:
            raise ValueError(
                f"索引 {uri} 里没有字段文档，请先运行 schema_indexing 构建索引。"
            )

        relations = index_client.load_all_relations()
        columns = [doc.column for doc in documents]

        service = cls(
            tables=tables,
            columns=columns,
            relations=relations,
            business_meta=None,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
            keyword_extractor=keyword_extractor,
            config=config,
        )

        # 索引里已经有算好的向量，直接装载，跳过重新编码。
        service.documents = documents
        service.keyword_index = BM25Index([doc.keyword_text for doc in documents])
        service.vector_index.documents = [doc.vector_text for doc in documents]
        service.vector_index.embeddings = np.asarray(embeddings, dtype=np.float32)

        return service

    def retrieve(
        self,
        query: str,
        keywords: Optional[Sequence[str]] = None,
    ) -> HybridSchemaRetrievalResult:
        """
        执行混合检索，并返回 SchemaGraph。

        Args:
            query: 用户自然语言 Query。
            keywords: 可选的核心关键词列表。
                如果传入，则直接使用该关键词列表。
                如果不传，则使用 keyword_extractor 自动抽取。

        Returns:
            HybridSchemaRetrievalResult: 包含关键词、RRF 结果、Rerank 结果和 SchemaGraph。
        """
        resolved_keywords = self._resolve_keywords(query, keywords)

        route_results = self._build_route_results(resolved_keywords)

        fusion_hits = self.rrf_client.fuse(
            route_results=route_results,
            keyword_count=len(resolved_keywords),
        )

        rerank_results = self._rerank(
            query=query,
            fusion_hits=fusion_hits,
            keyword_count=len(resolved_keywords),
        )

        schema_hits = self._build_schema_hits(
            rerank_results=rerank_results,
            fusion_hits=fusion_hits,
        )

        schema_hits = self._add_dominant_keyword_hits(
            keywords=resolved_keywords,
            schema_hits=schema_hits,
        )

        schema_hits = self._add_time_field_hits(
            query=query,
            schema_hits=schema_hits,
        )

        schema_graph = build_schema_graph(
            hits=schema_hits,
            tables=self.tables,
            all_columns=self.columns,
            relations=self.relations,
            include_join_columns=self.config.include_join_columns,
            include_label_columns=self.config.include_label_columns,
        )
        return HybridSchemaRetrievalResult(
            query=query,
            keywords=resolved_keywords,
            route_results=route_results,
            fusion_hits=fusion_hits,
            rerank_results=rerank_results,
            schema_hits=schema_hits,
            schema_graph=schema_graph,
        )

    def _find_dominant_keyword_docs(
        self,
        keywords: Sequence[str],
        covered_columns: Optional[Set[tuple]] = None,
    ) -> List[int]:
        """
        找出字面命中压倒性的字段下标。

        主判据是"分数断层"而不是绝对分数：排第一、且大幅甩开第二名。
        断层意味着这个词几乎只可能在说这一个字段——"直播间"除了下单渠道
        没有别的解释，"标价"除了 list_price 也没有。

        断层判据有个盲区：第二名往往是第一名的同义近邻，分数天然咬得死紧，
        谁也甩不开谁 3 倍，于是谁都不算压倒性。所以补一条覆盖判据——
        见 keyword_coverage_top_k 的说明。

        Args:
            keywords: 本次查询的关键词。
            covered_columns: 当前命中集已覆盖的 (表名, 字段名)。覆盖判据要用它
                判断"这个关键词有没有人替它说话"。不传时视为空集。
        """
        if self.config.dominant_keyword_ratio <= 0:
            return []

        dominant: List[int] = []

        for keyword in keywords:
            hits = self.keyword_index.search(
                keyword,
                top_k=max(2, self.config.max_dominant_per_query + 1),
            )

            if not hits:
                continue

            top_index, top_score = hits[0]

            if top_score < self.config.dominant_keyword_min_score:
                continue

            runner_up = hits[1][1] if len(hits) > 1 else 0.0

            # 判据一：断层。甩开第二名 N 倍，说明这个词几乎只可能在说这一个字段。
            # 这条与原实现完全一致，只补第一名。
            if (
                runner_up <= 0
                or top_score >= runner_up * self.config.dominant_keyword_ratio
            ):
                if top_index not in dominant:
                    dominant.append(top_index)
                continue

            # 判据二：覆盖。这个关键词的前 K 个强命中，一个都没进最终结果。
            #
            # 问的不是"这个字段够不够重要"，而是"这个检索意图有没有人替它说话"。
            # E24 里『北京用户』的前三名全军覆没，12 个名额被另一个关键词
            # 『订单笔数』带来的 dws 汇总层字段占满——筛选意图整个丢了。
            coverage_top_k = self.config.keyword_coverage_top_k

            if coverage_top_k <= 0:
                continue

            covered = covered_columns or set()

            # 代表必须和第一名**同级**。
            #
            # E51「已完成订单」：order_status 打 22.01 分却没入选，
            # 入选的是 finish_time（10.09，不到一半）。要是把它算作代表，
            # 这个词就被判定为"有人说话了"——而模型接下来干的正是拿
            # finish_time IS NOT NULL 去凑"已完成"，算出一个零告警的错数字。
            # 沾边的近义字段不是代表，只有同级的才是。
            representative_floor = max(
                self.config.dominant_keyword_min_score,
                top_score * self.config.dominant_keyword_tie_ratio,
            )

            leaders = [
                (index, score)
                for index, score in hits[:coverage_top_k]
                if score >= representative_floor
            ]

            if not leaders:
                continue

            def column_key(index: int) -> tuple:
                column = self.documents[index].column
                return (column.table_name, column.column_name)

            if any(column_key(index) in covered for index, _ in leaders):
                continue

            if top_index not in dominant:
                dominant.append(top_index)

            if not self.config.dominant_keyword_tie_expand:
                continue

            # 并列的同表近邻一起补回：分不清"北京"说的是 city 还是 province，
            # 两个都给，比赌一个错一个好。只收同一张表的，
            # 别顺手把别的表拖进来。
            top_table = self.documents[top_index].column.table_name
            tie_floor = top_score * self.config.dominant_keyword_tie_ratio

            for index, score in hits:
                if score < tie_floor:
                    break

                if self.documents[index].column.table_name != top_table:
                    continue

                if index not in dominant:
                    dominant.append(index)

        return dominant[: self.config.max_dominant_per_query]

    def _add_dominant_keyword_hits(
        self,
        keywords: Sequence[str],
        schema_hits: List[SchemaHit],
    ) -> List[SchemaHit]:
        """
        把字面压倒性命中的字段补进最终结果。

        这是对 RRF 丢失强度信息的补偿，和 include_join_columns / include_label_columns
        属于同一类做法：检索管线会漏掉某些"本该在里面"的字段，就在出口处补回来。
        """
        dominant_indices = self._find_dominant_keyword_docs(
            keywords=keywords,
            covered_columns={
                (hit.column.table_name, hit.column.column_name)
                for hit in schema_hits
            },
        )

        if not dominant_indices:
            return schema_hits

        existing = {
            (hit.column.table_name, hit.column.column_name)
            for hit in schema_hits
        }

        added = []

        for doc_index in dominant_indices:
            document = self.documents[doc_index]
            key = (document.column.table_name, document.column.column_name)

            if key in existing:
                continue

            schema_hits.append(
                SchemaHit(
                    doc_id=document.doc_id,
                    score=0.0,
                    column=document.column,
                    keyword_rank=1,
                )
            )
            existing.add(key)
            added.append(f"{key[0]}.{key[1]}")

        if added:
            emit(
                Codes.DOMINANT_KEYWORD_RESCUED,
                "字面命中压倒性的字段被精排淘汰，已强制补回",
                字段="、".join(added),
            )

        return schema_hits

    # 明确的时间约束：某年、某月、某日、季度、上下半年、上中下旬、第几周、具体日期。
    # 不收"最近""本月"这类相对说法——"最近一次下单"不是时间筛选。
    _TIME_CONSTRAINT = re.compile(
        r"\d{4}\s*年|\d{1,2}\s*月|\d{1,2}\s*[日号]|季度|[上下]半年|[上中下]旬"
        r"|第[一二三四五1-5]周|\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    )
    _QUERY_YEAR = re.compile(r"(\d{4})\s*年|(\d{4})[-/]\d{1,2}[-/]\d{1,2}")
    _COVERED_YEARS = re.compile(r"^(\d{4})-\d{2}-\d{2} 至 (\d{4})-\d{2}-\d{2}")

    def _add_time_field_hits(
        self,
        query: str,
        schema_hits: List[SchemaHit],
    ) -> List[SchemaHit]:
        """
        问题里有时间约束时，把最贴题的、数据覆盖该时段的时间字段补进结果。

        为什么需要它，见 HybridSchemaRetrievalConfig.time_field_guard。
        """
        if not self.config.time_field_guard or not self._TIME_CONSTRAINT.search(query):
            return schema_hits

        time_docs = [
            index
            for index, doc in enumerate(self.documents)
            if getattr(doc.column, "semantic_role", "") == "time"
            or self._COVERED_YEARS.match(getattr(doc.column, "value_range", "") or "")
        ]

        if not time_docs:
            return schema_hits

        years = {int(a or b) for a, b in self._QUERY_YEAR.findall(query)}

        def covers(index: int) -> bool:
            span = self._COVERED_YEARS.match(
                getattr(self.documents[index].column, "value_range", "") or ""
            )
            return span is not None and any(
                int(span.group(1)) <= year <= int(span.group(2)) for year in years
            )

        # 问 2024 年，就只在数据覆盖 2024 年的时间字段里挑；一个都不覆盖时（问的年份没有数据），
        # 照样补一个时间字段，让模型写得出筛选、查出"没有数据"，而不是丢掉条件。
        eligible = [index for index in time_docs if covers(index)] or time_docs

        best = self.rerank_client.rerank(
            query=query,
            documents=[
                RerankDocument(doc_index=index, text=self.documents[index].rerank_text)
                for index in eligible
            ],
            top_n=1,
        )

        if not best:
            return schema_hits

        document = self.documents[best[0].doc_index]
        key = (document.column.table_name, document.column.column_name)

        if any((hit.column.table_name, hit.column.column_name) == key for hit in schema_hits):
            return schema_hits

        schema_hits.append(
            SchemaHit(
                doc_id=document.doc_id,
                score=0.0,
                column=document.column,
            )
        )

        emit(
            Codes.TIME_FIELD_RESCUED,
            "问题里有时间约束，检索结果里却没有最贴题的时间字段，已补回",
            字段=f"{key[0]}.{key[1]}",
            候选数=len(eligible),
        )

        return schema_hits

    def _resolve_keywords(
        self,
        query: str,
        keywords: Optional[Sequence[str]],
    ) -> List[str]:
        """
        获取最终使用的核心关键词。
        """
        if keywords:
            return [item.strip() for item in keywords if item and item.strip()]

        if self.keyword_extractor is None:
            raise ValueError(
                "未传入 keywords，且未配置 keyword_extractor，无法自动抽取关键词。"
            )

        extracted_keywords = self.keyword_extractor.extract(query)

        if not extracted_keywords:
            raise ValueError(f"关键词抽取结果为空，query={query}")

        return extracted_keywords

    def _build_route_results(
        self,
        keywords: List[str],
    ) -> List[RouteRecallResult]:
        """
        执行 BM25 关键词召回和 Embedding 向量召回。
        """
        if self.keyword_index is None:
            raise RuntimeError("keyword_index 尚未初始化。")

        if self.vector_index is None:
            raise RuntimeError("vector_index 尚未初始化。")

        route_results: List[RouteRecallResult] = []

        for keyword in keywords:
            keyword_hits = self.keyword_index.search(
                keyword,
                top_k=self.config.per_keyword_top_k,
            )

            route_results.append(
                RouteRecallResult(
                    route_name="keyword",
                    query_term=keyword,
                    ranked_doc_indices=[
                        doc_index
                        for doc_index, _ in keyword_hits
                    ],
                )
            )

            vector_hits = self.vector_index.search(
                keyword,
                top_k=self.config.per_keyword_top_k,
            )

            route_results.append(
                RouteRecallResult(
                    route_name="vector",
                    query_term=keyword,
                    ranked_doc_indices=[
                        doc_index
                        for doc_index, _ in vector_hits
                    ],
                )
            )

        return route_results

    def _rerank(
        self,
        query: str,
        fusion_hits: List[RRFFusionHit],
        keyword_count: int,
    ) -> List[RerankResult]:
        """
        对 RRF 融合结果进行 Rerank 精排。
        """
        rerank_candidates = [
            RerankDocument(
                doc_index=hit.doc_index,
                text=self.documents[hit.doc_index].rerank_text,
            )
            for hit in fusion_hits
        ]

        rerank_top_n = self._calculate_rerank_top_n(
            keyword_count=keyword_count,
            candidate_count=len(rerank_candidates),
        )

        # 精排名额相对候选数过小，说明大部分候选在进模型之前就被砍掉了。
        # 这正是 docs/排查记录.md 问题一的形态：链路不报错，只是悄悄少给几个字段。
        if (
            len(rerank_candidates) >= self.config.recall_cap_warn_min_candidates
            and rerank_top_n < len(rerank_candidates) * self.config.recall_cap_warn_ratio
        ):
            emit(
                Codes.SCHEMA_RECALL_CAPPED,
                "精排名额相对候选数过小，可能已截掉需要的字段，"
                "建议调大 rerank_top_multiplier / rerank_min_top_n",
                关键词数=keyword_count,
                候选数=len(rerank_candidates),
                精排名额=rerank_top_n,
                保留比例=f"{rerank_top_n / len(rerank_candidates):.0%}",
            )

        return self.rerank_client.rerank(
            query=query,
            documents=rerank_candidates,
            top_n=rerank_top_n,
        )

    def _calculate_rerank_top_n(
        self,
        keyword_count: int,
        candidate_count: int,
    ) -> int:
        """
        根据关键词数量动态计算 Rerank 输出数量。
        """
        dynamic_top_n = keyword_count * self.config.rerank_top_multiplier

        top_n = max(
            self.config.rerank_min_top_n,
            min(dynamic_top_n, self.config.rerank_max_top_n),
        )

        return min(top_n, candidate_count)

    def _build_schema_hits(
        self,
        rerank_results: List[RerankResult],
        fusion_hits: List[RRFFusionHit],
    ) -> List[SchemaHit]:
        """
        将 Rerank 结果转换为 SchemaHit。
        """
        fusion_hit_map = {
            hit.doc_index: hit
            for hit in fusion_hits
        }

        schema_hits: List[SchemaHit] = []

        for result in rerank_results:
            doc = self.documents[result.doc_index]
            fusion_hit = fusion_hit_map.get(result.doc_index)

            best_rank_by_source = (
                fusion_hit.best_rank_by_source
                if fusion_hit is not None
                else {}
            )

            try:
                schema_hit = SchemaHit(
                    doc_id=doc.doc_id,
                    score=result.rerank_score,
                    column=doc.column,
                    keyword_rank=best_rank_by_source.get("keyword"),
                    vector_rank=best_rank_by_source.get("vector"),
                    rrf_score=fusion_hit.score if fusion_hit is not None else 0.0,
                    rerank_score=result.rerank_score,
                )
            except TypeError:
                # 兼容旧版 SchemaHit 结构。
                schema_hit = SchemaHit(
                    doc_id=doc.doc_id,
                    score=result.rerank_score,
                    column=doc.column,
                )

            schema_hits.append(schema_hit)

        return schema_hits

    def _build_indices(self) -> None:
        """
        构建 BM25 索引和向量索引。
        """
        keyword_texts = [
            doc.keyword_text
            for doc in self.documents
        ]

        self.keyword_index = BM25Index(keyword_texts)

        vector_texts = [
            doc.vector_text
            for doc in self.documents
        ]

        self.vector_index = VectorIndex(self.embedding_client)
        self.vector_index.build(vector_texts)

    def _build_documents(self) -> None:
        """
        构建混合检索字段文档。
        """
        self.documents = []

        for column in self.columns:
            table_meta = self.business_meta.get(column.table_name, {})
            column_meta = table_meta.get("columns", {}).get(column.column_name, {})

            keyword_text = (
                column_meta.get("keyword_text")
                or self._get_index_text(column, "keyword_text")
                or self._build_default_keyword_text(column)
            )

            vector_text = (
                column_meta.get("vector_text")
                or self._get_index_text(column, "vector_text")
                or self._build_default_vector_text(column)
            )

            rerank_text = (
                column_meta.get("rerank_text")
                or self._get_index_text(column, "rerank_text")
                or self._build_default_rerank_text(column)
            )

            self.documents.append(
                HybridFieldDocument(
                    doc_id=column.full_name,
                    column=column,
                    keyword_text=keyword_text,
                    vector_text=vector_text,
                    rerank_text=rerank_text,
                )
            )

    def _get_index_text(
        self,
        column: object,
        attr_name: str,
    ) -> str:
        """
        从 ColumnSchema.index_texts 中读取索引文本。
        """
        index_texts = getattr(column, "index_texts", None)

        if index_texts is None:
            return ""

        return getattr(index_texts, attr_name, "") or ""

    def _enrich_columns_with_business_meta(self) -> None:
        """
        将业务元数据补充回 ColumnSchema。
        """
        for column in self.columns:
            table_meta = self.business_meta.get(column.table_name, {})
            column_meta = table_meta.get("columns", {}).get(column.column_name, {})

            if table_meta:
                column.table_description = table_meta.get(
                    "description",
                    getattr(column, "table_description", ""),
                )
                column.table_aliases = table_meta.get(
                    "aliases",
                    getattr(column, "table_aliases", []),
                )

            if not column_meta:
                continue

            column.description = column_meta.get(
                "description",
                getattr(column, "description", ""),
            )
            column.aliases = column_meta.get(
                "aliases",
                getattr(column, "aliases", []),
            )
            column.semantic_role = column_meta.get(
                "semantic_role",
                getattr(column, "semantic_role", ""),
            )
            column.value_range = column_meta.get(
                "value_range",
                getattr(column, "value_range", ""),
            )
            column.data_distribution = column_meta.get(
                "data_distribution",
                getattr(column, "data_distribution", ""),
            )
            column.business_usage = column_meta.get(
                "business_usage",
                getattr(column, "business_usage", ""),
            )

            if "samples" in column_meta:
                column.samples = [
                    str(item)
                    for item in column_meta["samples"]
                ]

    def _build_default_keyword_text(
        self,
        column: object,
    ) -> str:
        """
        构建默认关键词索引文本。
        """
        parts = [
            getattr(column, "database", ""),
            getattr(column, "table_name", ""),
            getattr(column, "column_name", ""),
            getattr(column, "data_type", ""),
            getattr(column, "description", ""),
            " ".join(getattr(column, "aliases", []) or []),
            " ".join(getattr(column, "samples", [])[:5] or []),
        ]

        return "\n".join(part for part in parts if part)

    def _build_default_vector_text(
        self,
        column: object,
    ) -> str:
        """
        构建默认向量索引文本。
        """
        parts = [
            f"字段名：{getattr(column, 'column_name', '')}",
            f"所属表：{getattr(column, 'table_name', '')}",
            f"所属表业务含义：{getattr(column, 'table_description', '')}",
            f"字段含义：{getattr(column, 'description', '')}",
        ]

        aliases = getattr(column, "aliases", []) or []
        if aliases:
            parts.append(f"字段别名：{', '.join(aliases)}")

        business_usage = getattr(column, "business_usage", "")
        if business_usage:
            parts.append(f"业务用途：{business_usage}")

        semantic_role = getattr(column, "semantic_role", "")
        if semantic_role:
            parts.append(f"字段角色：{semantic_role}")

        return "\n".join(part for part in parts if part)

    def _build_default_rerank_text(
        self,
        column: object,
    ) -> str:
        """
        构建默认 Rerank 文本。
        """
        parts = [
            f"字段：{getattr(column, 'table_name', '')}.{getattr(column, 'column_name', '')}",
            f"数据类型：{getattr(column, 'data_type', '')}",
            f"所属表业务含义：{getattr(column, 'table_description', '')}",
            f"字段含义：{getattr(column, 'description', '')}",
        ]

        aliases = getattr(column, "aliases", []) or []
        if aliases:
            parts.append(f"字段别名：{', '.join(aliases)}")

        semantic_role = getattr(column, "semantic_role", "")
        if semantic_role:
            parts.append(f"字段角色：{semantic_role}")

        value_range = getattr(column, "value_range", "")
        if value_range:
            parts.append(f"取值范围：{value_range}")

        data_distribution = getattr(column, "data_distribution", "")
        if data_distribution:
            parts.append(f"数据分布：{data_distribution}")

        business_usage = getattr(column, "business_usage", "")
        if business_usage:
            parts.append(f"业务用途：{business_usage}")

        samples = getattr(column, "samples", []) or []
        if samples:
            parts.append(f"样例值：{', '.join(samples[:8])}")

        return "\n".join(part for part in parts if part)


if __name__ == "__main__":
    # 这里复用完整链路 Demo 中的测试数据库和业务元数据。
    # 该 import 只用于示例，不影响服务类本身被其他模块导入。
    from llm_config import has_chat_provider
    from schema_retrieval.hybrid_rerank_schema_demo import (
        create_demo_database,
        get_business_meta,
    )

    db_path = create_demo_database()
    business_meta = get_business_meta()

    embedding_client = AliyunEmbeddingClient(
        AliyunEmbeddingConfig(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            embedding_url="https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
            model="text-embedding-v4",
            dimensions=1024,
        )
    )

    # 如果你想使用大模型自动抽取关键词，就配置 keyword_extractor。
    # 如果 retrieve() 中直接传 keywords，则可以不配置 keyword_extractor。
    keyword_extractor = None

    if has_chat_provider():
        keyword_extractor = AliyunKeywordExtractor(
            AliyunKeywordExtractorConfig(
                api_key=os.getenv("DASHSCOPE_API_KEY", ""),
                model="qwen-plus",
            )
        )

    rerank_client = AliyunRerankClient(
        AliyunRerankConfig(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            workspace_id=os.getenv("DASHSCOPE_WORKSPACE_ID", ""),

            # 这里按你的要求默认使用 qwen-rerank。
            # 如果你的环境使用 qwen3-rerank，可以改为：
            # model="qwen3-rerank"
            model=os.getenv("DASHSCOPE_RERANK_MODEL", "qwen-rerank"),
        )
    )

    service = HybridSchemaRetrievalService.from_sqlite(
        db_path=db_path,
        database_name="demo_finance",
        business_meta=business_meta,
        embedding_client=embedding_client,
        rerank_client=rerank_client,
        keyword_extractor=keyword_extractor,
        config=HybridSchemaRetrievalConfig(
            per_keyword_top_k=20,
            include_join_columns=True,
            rrf_config=RRFFusionConfig(
                rrf_k=60,
                truncate_multiplier=6,
                min_fused_top_k=10,
                max_fused_top_k=50,
                final_top_k=20,
                route_weights={
                    "keyword": 1.0,
                    "vector": 1.0,
                },
            ),
            rerank_top_multiplier=2,
            rerank_min_top_n=2,
            rerank_max_top_n=20,
        ),
        sample_size=5,
    )

    query = "查询总交易笔数大于50000的利率是多少"

    # 示例 1：手动传关键词。
    # 如果你想强制使用大模型抽取关键词，把 keywords 参数删掉即可。
    result = service.retrieve(
        query=query,
        keywords=["总交易笔数", "利率"],
    )

    print("=" * 80)
    print("Hybrid Schema Retrieval Service Demo")
    print("=" * 80)

    print("\n[1] Query:")
    print(result.query)

    print("\n[2] Keywords:")
    print("，".join(result.keywords))

    print("\n[3] RRF fusion hits:")
    for rank, hit in enumerate(result.fusion_hits, start=1):
        doc = service.documents[hit.doc_index]
        col = doc.column

        print(
            f"{rank}. {col.table_name}.{col.column_name} "
            f"rrf_score={hit.score:.6f} "
            f"sources={hit.sources} "
            f"matched_terms={hit.matched_terms} "
            f"best_rank_by_source={hit.best_rank_by_source}"
        )

    print("\n[4] Rerank results:")
    for rank, item in enumerate(result.rerank_results, start=1):
        doc = service.documents[item.doc_index]
        col = doc.column

        print(
            f"{rank}. {col.table_name}.{col.column_name} "
            f"rerank_score={item.rerank_score:.6f}"
        )

    print("\n[5] Schema graph prompt context:")
    print(result.schema_graph.to_prompt_context())
