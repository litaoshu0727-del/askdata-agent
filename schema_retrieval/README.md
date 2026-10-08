# schema_retrieval

字段级 Schema 检索：从问题里抽关键词，在全部字段里找出这道题要用的那些，组装成 SchemaGraph
（字段 + 表关系）交给 CoT 规划。

主链路用的是 `HybridSchemaRetrievalService`（[hybrid_schema_retrieval_service.py](hybrid_schema_retrieval_service.py)）：

```text
关键词 → BM25 + 向量两路召回 → RRF 融合（每个关键词自己的前 3 名保底进候选池）→ 精排
      → 关键词覆盖：每个关键词至少留一个字段代表
      → 强命中补回：字面压倒性命中却被精排砍掉的字段补回来
      → 时间约束保底：问题有时间约束、结果里却没有时间字段时，补一个数据覆盖该时段的
      → SchemaGraph：关键词落在的表之间不连通时，沿外键补上桥接表（只带关联键）
```

## 文件

| 文件 | 内容 |
|---|---|
| `hybrid_schema_retrieval_service.py` | 主链路用的检索服务，`from_sqlite` / `from_milvus` 两种构建方式 |
| `sqlite_loader.py` | 解析 SQLite Schema：字段、外键、样例值、时间字段的覆盖年份 |
| `document_builder.py` | 字段级检索文档 |
| `graph_builder.py` | SchemaGraph 构建 |
| `tokenizer.py` `bm25.py` `retriever.py` | 中英文分词与 BM25 召回 |
| `vector_index.py` | 内存向量索引 |
| `rrf_fusion_client.py` | RRF 融合 |
| `keyword_extractor_client.py` | 大模型关键词抽取 |
| `local_embedding_client.py` `local_rerank_client.py` | 本地 bge 向量与精排（主链路在用） |
| `embedding_client.py` `rerank_client.py` | 阿里云百炼向量与精排 |
| `*_demo.py` | 原作者的分步 Demo，见下文 |

## 几条要知道的事

- **检索参数要随 Schema 规模放大。**精排名额 = 关键词数 × multiplier。默认按大库参数，
  只有 9 个字段的 trade 库显式用小参数，见
  [检索参数要随 Schema 规模放大](../docs/实验记录.md#检索参数要随-schema-规模放大)
- **别手写 `rerank_text`。**手写的精排文本会整个替换自动生成的文本，而自动生成的那份带着
  表描述、别名和样例值。两个库手写的都删了，删后召回反而更好，见
  [第二套留出集](../docs/实验记录.md#第二套留出集修-chinook-精排在没见过的题上验证)
- **候选池按关键词保底。**全局 RRF 的总分实际上成了"出现在几个列表里"，只被一个关键词
  命中的字段，哪怕在这个词下排第 1，也会被挤出候选池，后面的精排和补回都碰不到它。
  `RRFFusionConfig.per_term_top_k`（默认 3）让每个词的前几名保底进池，见
  [候选池按关键词保底](../docs/实验记录.md#候选池按关键词保底)
- **连接路径上的桥接表。**关联键只在一条关系两端的表都选中时才补；路径中间那张没人问到的表
  （客户→发票→发票明细→曲目里的发票、明细）不补，图就断了。按每个关键词排第 1 的字段落在
  哪些表判断要不要连，没有锚点的块当噪声不连。`bridge_max_tables`（默认 3）控制上限，见
  [连接路径上的桥接表](../docs/实验记录.md#连接路径上的桥接表)
- **时间字段的覆盖年份不进任何索引文本和提示词**，只给时间约束保底用，见
  [只留保底](../docs/实验记录.md#只留保底)

## 分步 Demo

原作者的教学 Demo，在 trade 库上一步步演示召回过程，用的是阿里云百炼客户端。没配
`DASHSCOPE_API_KEY` 和 `DASHSCOPE_WORKSPACE_ID` 时，向量和精排走 Mock，降级记录里会写明。

```bash
python -m schema_retrieval.keyword_recall_demo          # 关键词召回
python -m schema_retrieval.vector_recall_demo           # 向量召回
python -m schema_retrieval.hybrid_recall_demo           # 关键词 + 向量 + RRF
python -m schema_retrieval.hybrid_rerank_schema_demo    # 再加精排和 SchemaGraph
```

要看主链路的真实检索结果，用 `python -m askdata_pipeline.ecommerce_demo` 或 Web 界面。
