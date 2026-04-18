# Chunking Evaluation Report v4

**PDF:** `knowledge_base/05_crad_10.7544_issn1000-1239.202110867.pdf`

**Generated:** 2026-04-14 16:30:17

**Embedding:** SentenceTransformerEmbedding  
**Mode selection:** all  
**Active modes:** Page-Mode, Structured, Structured+Simple, Structured+HeuristicV2, Structured+Hybrid+SoftV3

## 1. Evaluation Config

- Cases: **18** query cases
- Top-k: **5**
- Dense candidate top_n: **30**
- Lexical candidate top_n: **30**
- Fusion candidate top_n: **30**
- Fusion method: **RRF (k=60)**
- Fairness note: all modes use the same dense retrieval budget; `structured_hybrid` adds a lexical candidate pool of the same size before fusion.
- Soft_v3 formula: `0.55*fusion_norm + 0.25*dense_norm + 0.10*lexical_norm + 0.10*keyword_overlap + intent bonuses - generic_title_penalty`
- Soft_v3 intent bonuses are small additive terms for `section_title match`, `block_type match`, `explicit anchor`, and `page-1 front matter`; it does not hard override the base retrieval score.

### Metric Definitions

- `hit@k = 1` if at least one correct result appears within top-k, else `0`.
- `avg_match_rate@k = (# correct results within top-k) / k_actual`, where `k_actual = min(k, returned_results)`.
- `MRR = 1 / first_correct_rank` if a correct result exists, else `0`.
- `first_correct_rank` is the 1-based rank of the first correct result; if no correct result exists, it is reported as `-1` in raw metrics and omitted from the mean-positive aggregate.

## 2. Chunk Statistics

| Metric | Page-Mode | Structured |
|--------|-----------|------------|
| Total chunks | 21 | 326 |
| Avg chars | 2500.4 | 162.1 |
| page_start complete | 0.048 | 1.0 |
| section_title non-empty | 0.0 | 0.985 |
| block_type known | 0.0 | 1.0 |
| block_type dist | (n/a) | {'heading': 150, 'paragraph': 163, 'caption': 13} |

## 3. Automatic Metrics Summary

_Mean over 18 cases_

### 3a. Page / Section / Keyword Hit (@1 / @3 / @5)

| Mode | page_hit@1 | page_hit@3 | page_hit@5 | section_hit@1 | section_hit@3 | section_hit@5 | keyword_hit@1 | keyword_hit@3 | keyword_hit@5 |
|------|------------|------------|------------|---------------|---------------|---------------|---------------|---------------|---------------|
| Page-Mode | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.722 | 0.833 | 0.889 |
| Structured | 0.389 | 0.833 | 0.889 | 0.389 | 0.556 | 0.556 | 0.611 | 0.778 | 0.778 |
| Structured+Simple | 0.444 | 0.722 | 0.889 | 0.444 | 0.556 | 0.556 | 0.611 | 0.778 | 0.778 |
| Structured+HeuristicV2 | 0.444 | 0.722 | 0.833 | 0.5 | 0.556 | 0.611 | 0.722 | 0.778 | 0.778 |
| Structured+Hybrid+SoftV3 | 0.667 | 0.833 | 0.944 | 0.611 | 0.778 | 0.833 | 0.778 | 0.833 | 0.889 |

### 3b. Block-Type Hit, First Correct Rank, MRR, Title Attraction

| Mode | bt_hit@1 | bt_hit@3 | bt_hit@5 | first_correct_rank(page) | first_correct_rank(section) | mrr_page | mrr_section | title_attraction% |
|------|----------|----------|----------|--------------------------|-----------------------------|----------|-------------|------------------|
| Page-Mode | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0% |
| Structured | 0.611 | 0.778 | 0.778 | 1.812 | 1.4 | 0.606 | 0.463 | 5.6% |
| Structured+Simple | 0.667 | 0.778 | 0.778 | 2.125 | 1.3 | 0.594 | 0.491 | 5.6% |
| Structured+HeuristicV2 | 0.667 | 0.778 | 0.778 | 1.867 | 1.364 | 0.593 | 0.542 | 0.0% |
| Structured+Hybrid+SoftV3 | 0.833 | 0.889 | 0.944 | 1.647 | 1.533 | 0.759 | 0.69 | 5.6% |

### 3c. Avg Match Rate (@1 / @3 / @5)

| Mode | page_avg_match_rate@1 | page_avg_match_rate@3 | page_avg_match_rate@5 | section_avg_match_rate@1 | section_avg_match_rate@3 | section_avg_match_rate@5 | keyword_avg_match_rate@1 | keyword_avg_match_rate@3 | keyword_avg_match_rate@5 |
|------|-----------------------|-----------------------|-----------------------|--------------------------|--------------------------|--------------------------|--------------------------|--------------------------|--------------------------|
| Page-Mode | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.722 | 0.555 | 0.6 |
| Structured | 0.389 | 0.333 | 0.267 | 0.389 | 0.204 | 0.144 | 0.611 | 0.407 | 0.3 |
| Structured+Simple | 0.444 | 0.278 | 0.256 | 0.444 | 0.204 | 0.156 | 0.611 | 0.389 | 0.3 |
| Structured+HeuristicV2 | 0.444 | 0.278 | 0.222 | 0.5 | 0.222 | 0.178 | 0.722 | 0.37 | 0.289 |
| Structured+Hybrid+SoftV3 | 0.667 | 0.352 | 0.311 | 0.611 | 0.389 | 0.333 | 0.778 | 0.537 | 0.478 |

## 4. Per-Case Metrics (standard hit@5)

| Case | _p@5_ | _s@5_ | _k@5_ | _bt@5_ | _p@5_ | _s@5_ | _k@5_ | _bt@5_ | _p@5_ | _s@5_ | _k@5_ | _bt@5_ | _p@5_ | _s@5_ | _k@5_ | _bt@5_ | _p@5_ | _s@5_ | _k@5_ | _bt@5_ |
|------|---|---|---|---|---|
| **title_ch** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 1.0 |
| **author_email** | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| **abstract_en** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 1.0 |
| **abstract_cn** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **keywords_cn** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **recv_date** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **funding** | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **sec_1_1** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **sec_1_2** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **sec_1_3** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **model_cut** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **compression** | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **fig1** | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **fig2** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **table1** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **table2** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| **def_edge_intel** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| **overall_arch** | 0.0 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

## 5. Representative Query Comparison

### 1. [title_ch] 这篇论文的标题是什么？

*Notes: 标题查询，允许 page 1 heading 获得明显加权。*

**Page-Mode** (top-3):

  [1] p? [unknown] section='' score=0.3898 dense=0.3898 lexical=9.7218 fusion=0.3898 text=Gartner 指出2022 年将有75% 的企业数据在边 缘侧产生 [1]，IDC 预测2025 年将有416 亿个边缘侧设 备实现互联数据量达79.4 ZB...
  [2] p? [unknown] section='' score=0.3438 dense=0.3438 lexical=10.2893 fusion=0.3438 text=架构（实现）搜索等.推理阶段可对模型进行2 次处理， 结合早期退出、模型量化、神经网络架构（实现）搜 索等方式对模型进行进一步修改，以及在支持节点 协同的情况下...
  [3] p? [unknown] section='' score=0.3411 dense=0.3411 lexical=5.9237 fusion=0.3411 text=预处理 [115]、计算一部分中间输出结果外，还可与早期 退出结合 [54,116]，将一部分具有推理功能的分支部署在 边端，当边端推理结果不满足需求时，通过云...

**Structured** (top-3):

  [1] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.6801 dense=0.6801 lexical=7.2075 fusion=0.6801 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [2] p4 [heading] section='与已有综述研究的比较以及本文的贡献' score=0.6395 dense=0.6395 lexical=14.5179 fusion=0.6395 text=1.3 与已有综述研究的比较以及本文的贡献...
  [3] p4 [caption] section='模型切割' score=0.6294 dense=0.6294 lexical=2.4021 fusion=0.6294 text=图4 所示，按照模型的内部结构可通过纵切、横切及...

**Structured+Simple** (top-3):

  [1] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=1.0 dense=0.6801 lexical=7.2075 fusion=0.6801 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [2] p4 [heading] section='与已有综述研究的比较以及本文的贡献' score=0.8614 dense=0.6395 lexical=14.5179 fusion=0.6395 text=1.3 与已有综述研究的比较以及本文的贡献...
  [3] p4 [caption] section='模型切割' score=0.8267 dense=0.6294 lexical=2.4021 fusion=0.6294 text=图4 所示，按照模型的内部结构可通过纵切、横切及...

**Structured+HeuristicV2** (top-3):

  [1] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=1.0 dense=0.6801 lexical=7.2075 fusion=0.6801 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [2] p4 [heading] section='与已有综述研究的比较以及本文的贡献' score=0.8614 dense=0.6395 lexical=14.5179 fusion=0.6395 text=1.3 与已有综述研究的比较以及本文的贡献...
  [3] p4 [caption] section='模型切割' score=0.8267 dense=0.6294 lexical=2.4021 fusion=0.6294 text=图4 所示，按照模型的内部结构可通过纵切、横切及...

**Structured+Hybrid+SoftV3** (top-3):

  [1] p4 [heading] section='与已有综述研究的比较以及本文的贡献' score=0.9583 dense=0.6395 lexical=14.5179 fusion=0.0323 text=1.3 与已有综述研究的比较以及本文的贡献...
  [2] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.8463 dense=0.6801 lexical=7.2075 fusion=0.0297 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [3] p1 [heading] section='' score=0.6056 dense=0.5971 lexical=2.6793 fusion=0.0156 text=面向边缘智能的协同推理综述...

### 2. [abstract_cn] 中文摘要主要讲了什么？

*Notes: 摘要查询，page 1 与 section_title 应获得加权。*

**Page-Mode** (top-3):

  [1] p? [unknown] section='' score=0.4605 dense=0.4605 lexical=5.7604 fusion=0.4605 text=预处理 [115]、计算一部分中间输出结果外，还可与早期 退出结合 [54,116]，将一部分具有推理功能的分支部署在 边端，当边端推理结果不满足需求时，通过云...
  [2] p? [unknown] section='' score=0.4423 dense=0.4423 lexical=6.6908 fusion=0.4423 text=架构（实现）搜索等.推理阶段可对模型进行2 次处理， 结合早期退出、模型量化、神经网络架构（实现）搜 索等方式对模型进行进一步修改，以及在支持节点 协同的情况下...
  [3] p? [unknown] section='' score=0.434 dense=0.434 lexical=5.504 fusion=0.434 text=Gartner 指出2022 年将有75% 的企业数据在边 缘侧产生 [1]，IDC 预测2025 年将有416 亿个边缘侧设 备实现互联数据量达79.4 ZB...

**Structured** (top-3):

  [1] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.6716 dense=0.6716 lexical=3.9689 fusion=0.6716 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [2] p1 [heading] section='' score=0.6447 dense=0.6447 lexical=0.0 fusion=0.6447 text=面向边缘智能的协同推理综述...
  [3] p9 [caption] section='整体架构' score=0.6416 dense=0.6416 lexical=3.6347 fusion=0.6416 text=图 7 主流的边缘计算协同推理架构...

**Structured+Simple** (top-3):

  [1] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=1.0 dense=0.6716 lexical=3.9689 fusion=0.6716 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [2] p9 [caption] section='整体架构' score=0.8758 dense=0.6416 lexical=3.6347 fusion=0.6416 text=图 7 主流的边缘计算协同推理架构...
  [3] p1 [heading] section='' score=0.7689 dense=0.6447 lexical=0.0 fusion=0.6447 text=面向边缘智能的协同推理综述...

**Structured+HeuristicV2** (top-3):

  [1] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=1.0 dense=0.6716 lexical=3.9689 fusion=0.6716 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [2] p9 [caption] section='整体架构' score=0.8758 dense=0.6416 lexical=3.6347 fusion=0.6416 text=图 7 主流的边缘计算协同推理架构...
  [3] p1 [heading] section='关键词 边缘计算；边缘智能；机器学习；边缘协同推理；动态场景' score=0.7756 dense=0.6173 lexical=2.7372 fusion=0.6173 text=中图法分类号 TP391...

**Structured+Hybrid+SoftV3** (top-3):

  [1] p4 [paragraph] section='边缘协同推理的智能化方法' score=0.8099 dense=0.5385 lexical=12.6539 fusion=0.0306 text=主流的深度神经网络模型大小通常为几兆字节 甚至几百兆字节，计算量较高给低配置的边缘节点 带来了挑战 [44]，因此需要考虑如何在边缘节点上对 模型进行部署. 一...
  [2] p1 [paragraph] section='摘 要' score=0.754 dense=0.4311 lexical=9.4976 fusion=0.0253 text=近年来，信息技术的不断变革伴随数据量的急剧爆发，使主流的云计算解决方案面临实时性差、 带宽受限、高能耗、维护费用高、隐私安全等问题. 边缘智能的出现与快速发展有...
  [3] p4 [paragraph] section='与已有综述研究的比较以及本文的贡献' score=0.705 dense=0.4623 lexical=10.22 fusion=0.0269 text=由于推理过程中所用机器学习模型规模大、复 杂性高，限制了推理关键技术在边缘计算场景下的 训练与应用.目前，有研究者针对模型的推理内容进 行了总结.文献[39] ...

### 3. [fig2] 图 2 反映了什么内容？

*Notes: figure 编号精确定位。*

**Page-Mode** (top-3):

  [1] p? [unknown] section='' score=0.3426 dense=0.3426 lexical=5.2945 fusion=0.3426 text=Gartner 指出2022 年将有75% 的企业数据在边 缘侧产生 [1]，IDC 预测2025 年将有416 亿个边缘侧设 备实现互联数据量达79.4 ZB...
  [2] p? [unknown] section='' score=0.3307 dense=0.3307 lexical=6.6913 fusion=0.3307 text=架构（实现）搜索等.推理阶段可对模型进行2 次处理， 结合早期退出、模型量化、神经网络架构（实现）搜 索等方式对模型进行进一步修改，以及在支持节点 协同的情况下...
  [3] p? [unknown] section='' score=0.2769 dense=0.2769 lexical=2.6984 fusion=0.2769 text=时的不同模型问题；分支切换灵活性及资源分配粒 度问题. 同时，如2.2 节所述，尽管目前已经呈现出不 同技术的融合态势，但在协同环境下，边缘协同推理 智能化方法...

**Structured** (top-3):

  [1] p4 [caption] section='模型切割' score=0.6687 dense=0.6687 lexical=8.374 fusion=0.6687 text=图4 所示，按照模型的内部结构可通过纵切、横切及...
  [2] p3 [caption] section='边缘协同推理的整体过程' score=0.6029 dense=0.6029 lexical=10.2783 fusion=0.6029 text=图 2 协同推理关键技术出现时间...
  [3] p11 [caption] section='整体架构' score=0.5901 dense=0.5901 lexical=0.0 fusion=0.5901 text=表 2    不同架构的比较...

**Structured+Simple** (top-3):

  [1] p4 [caption] section='模型切割' score=1.15 dense=0.6687 lexical=8.374 fusion=0.6687 text=图4 所示，按照模型的内部结构可通过纵切、横切及...
  [2] p3 [caption] section='边缘协同推理的整体过程' score=0.9618 dense=0.6029 lexical=10.2783 fusion=0.6029 text=图 2 协同推理关键技术出现时间...
  [3] p11 [caption] section='整体架构' score=0.9251 dense=0.5901 lexical=0.0 fusion=0.5901 text=表 2    不同架构的比较...

**Structured+HeuristicV2** (top-3):

  [1] p4 [caption] section='模型切割' score=1.18 dense=0.6687 lexical=8.374 fusion=0.6687 text=图4 所示，按照模型的内部结构可通过纵切、横切及...
  [2] p3 [caption] section='边缘协同推理的整体过程' score=0.9918 dense=0.6029 lexical=10.2783 fusion=0.6029 text=图 2 协同推理关键技术出现时间...
  [3] p11 [caption] section='整体架构' score=0.9551 dense=0.5901 lexical=0.0 fusion=0.5901 text=表 2    不同架构的比较...

**Structured+Hybrid+SoftV3** (top-3):

  [1] p3 [caption] section='边缘协同推理的整体过程' score=1.1814 dense=0.6029 lexical=10.2783 fusion=0.0325 text=图 2 协同推理关键技术出现时间...
  [2] p4 [caption] section='模型切割' score=1.014 dense=0.6687 lexical=8.374 fusion=0.0325 text=图4 所示，按照模型的内部结构可通过纵切、横切及...
  [3] p5 [caption] section='模型切割' score=0.8152 dense=0.5298 lexical=4.316 fusion=0.0294 text=图 4 模型切割方式...

### 4. [table1] 表1 比较了哪些模型切割方法？

*Notes: table_query，图类 caption 不应获得同等高权重。*

**Page-Mode** (top-3):

  [1] p? [unknown] section='' score=0.3805 dense=0.3805 lexical=9.5456 fusion=0.3805 text=时的不同模型问题；分支切换灵活性及资源分配粒 度问题. 同时，如2.2 节所述，尽管目前已经呈现出不 同技术的融合态势，但在协同环境下，边缘协同推理 智能化方法...
  [2] p? [unknown] section='' score=0.3757 dense=0.3757 lexical=10.1963 fusion=0.3757 text=Gartner 指出2022 年将有75% 的企业数据在边 缘侧产生 [1]，IDC 预测2025 年将有416 亿个边缘侧设 备实现互联数据量达79.4 ZB...
  [3] p? [unknown] section='' score=0.3641 dense=0.3641 lexical=13.3599 fusion=0.3641 text=解决. 文献[8] 指出,“边缘”是一个连续统，那么，协 同推理的架构主要关注点则是如何调集连续统中的 资源. 本文按照资源及数据的协同处理方式，从云与 边的角...

**Structured** (top-3):

  [1] p5 [caption] section='模型切割' score=0.9579 dense=0.9579 lexical=73.0413 fusion=0.9579 text=表 1    模型切割方法比较...
  [2] p4 [heading] section='与已有综述研究的比较以及本文的贡献' score=0.6259 dense=0.6259 lexical=14.6878 fusion=0.6259 text=1.3 与已有综述研究的比较以及本文的贡献...
  [3] p5 [caption] section='模型切割' score=0.6213 dense=0.6213 lexical=41.22 fusion=0.6213 text=图 4 模型切割方式...

**Structured+Simple** (top-3):

  [1] p5 [caption] section='模型切割' score=1.45 dense=0.9579 lexical=73.0413 fusion=0.9579 text=表 1    模型切割方法比较...
  [2] p5 [caption] section='模型切割' score=0.594 dense=0.6213 lexical=41.22 fusion=0.6213 text=图 4 模型切割方式...
  [3] p11 [caption] section='整体架构' score=0.5359 dense=0.5861 lexical=18.6106 fusion=0.5861 text=表 2    不同架构的比较...

**Structured+HeuristicV2** (top-3):

  [1] p5 [caption] section='模型切割' score=1.58 dense=0.9579 lexical=73.0413 fusion=0.9579 text=表 1    模型切割方法比较...
  [2] p5 [caption] section='模型切割' score=0.624 dense=0.6213 lexical=41.22 fusion=0.6213 text=图 4 模型切割方式...
  [3] p11 [caption] section='整体架构' score=0.5659 dense=0.5861 lexical=18.6106 fusion=0.5861 text=表 2    不同架构的比较...

**Structured+Hybrid+SoftV3** (top-3):

  [1] p5 [caption] section='模型切割' score=1.3867 dense=0.9579 lexical=73.0413 fusion=0.0328 text=表 1    模型切割方法比较...
  [2] p5 [caption] section='模型切割' score=1.0173 dense=0.6213 lexical=41.22 fusion=0.032 text=图 4 模型切割方式...
  [3] p4 [caption] section='模型切割' score=0.9215 dense=0.5698 lexical=26.9704 fusion=0.0301 text=图4 所示，按照模型的内部结构可通过纵切、横切及...

### 5. [def_edge_intel] 边缘智能的定义是什么？

*Notes: concept_query，正文 paragraph 应优于论文总标题。*

**Page-Mode** (top-3):

  [1] p? [unknown] section='' score=0.3686 dense=0.3686 lexical=7.4971 fusion=0.3686 text=Gartner 指出2022 年将有75% 的企业数据在边 缘侧产生 [1]，IDC 预测2025 年将有416 亿个边缘侧设 备实现互联数据量达79.4 ZB...
  [2] p? [unknown] section='' score=0.3529 dense=0.3529 lexical=6.4807 fusion=0.3529 text=何利用分布式网络中的资源还未形成系统性认识， 多为简单的智能算法相互组合，节点间协同性不强， 未涉及到与深度学习技术的结合，能支持的智能业 务有限. 边缘协同智...
  [3] p? [unknown] section='' score=0.3236 dense=0.3236 lexical=4.6336 fusion=0.3236 text=解决. 文献[8] 指出,“边缘”是一个连续统，那么，协 同推理的架构主要关注点则是如何调集连续统中的 资源. 本文按照资源及数据的协同处理方式，从云与 边的角...

**Structured** (top-3):

  [1] p1 [heading] section='' score=0.8348 dense=0.8348 lexical=27.0447 fusion=0.8348 text=面向边缘智能的协同推理综述...
  [2] p2 [caption] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.7989 dense=0.7989 lexical=28.298 fusion=0.7989 text=图 1 边缘智能发展趋势...
  [3] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.7808 dense=0.7808 lexical=28.054 fusion=0.7808 text=关键词进行检索，得到的关于边缘智能的文献数量...

**Structured+Simple** (top-3):

  [1] p2 [caption] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.9266 dense=0.7989 lexical=28.298 fusion=0.7989 text=图 1 边缘智能发展趋势...
  [2] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.8896 dense=0.7808 lexical=28.054 fusion=0.7808 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [3] p1 [heading] section='' score=0.88 dense=0.8348 lexical=27.0447 fusion=0.8348 text=面向边缘智能的协同推理综述...

**Structured+HeuristicV2** (top-3):

  [1] p2 [caption] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.9266 dense=0.7989 lexical=28.298 fusion=0.7989 text=图 1 边缘智能发展趋势...
  [2] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.8896 dense=0.7808 lexical=28.054 fusion=0.7808 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [3] p1 [heading] section='' score=0.85 dense=0.8348 lexical=27.0447 fusion=0.8348 text=面向边缘智能的协同推理综述...

**Structured+Hybrid+SoftV3** (top-3):

  [1] p2 [heading] section='关键词进行检索，得到的关于边缘智能的文献数量' score=1.0147 dense=0.7808 lexical=28.054 fusion=0.032 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [2] p2 [caption] section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.996 dense=0.7989 lexical=28.298 fusion=0.0325 text=图 1 边缘智能发展趋势...
  [3] p4 [heading] section='边缘协同推理的智能化方法' score=0.8972 dense=0.7053 lexical=21.4819 fusion=0.0299 text=2.1 边缘协同推理的智能化方法...

## 6. Conclusions

- Chunking gain: Structured page_hit@5=0.889 vs Page-Mode=0.0; Structured section_hit@5=0.556 vs Page-Mode=0.0.
- Page-mode keyword_hit@5 may still read higher because it has 21 large chunks averaging 2500.4 chars, while structured mode has 326 smaller chunks averaging 162.1 chars. This is a **big-chunk keyword bias**, not evidence that page-mode retrieval is better.
- Interpretation: structured chunking already improved localization and metadata completeness; the remaining instability is mainly in retrieval / ranking rather than chunk construction.
- Ranking delta: Structured+Simple page_hit@5=0.889 vs Structured=0.889.
- Ranking delta: Structured+HeuristicV2 page_hit@5=0.833 vs Structured=0.889; title_attraction=0.0% vs 5.6%.
- Hybrid + Soft_v3 delta: Structured+Hybrid+SoftV3 page_hit@5=0.944 vs Structured=0.889; section_hit@5=0.833 vs 0.556; title_attraction=5.6% vs 5.6%.
- Interpretation: this comparison isolates retrieval / ranking changes on top of the existing structured chunking baseline.
