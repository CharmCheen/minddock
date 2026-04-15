# Chunking Evaluation Report v5

**PDF:** `knowledge_base/05_crad_10.7544_issn1000-1239.202110867.pdf`

**Generated:** 2026-04-15 10:48:17

**Embedding:** SentenceTransformerEmbedding  
**Focus:** front matter ranking bias reduction on top of existing structured chunking + hybrid retrieval

## 1. Evaluation Config

- Cases: **16** total = **13** front matter + **3** control
- Top-k: **5**
- Dense candidate top_n: **30**
- Lexical candidate top_n: **30**
- Fusion candidate top_n: **30**
- Fusion method: **RRF (k=60)**
- Compared modes: `structured_hybrid`, `structured+hybrid+soft_v3`, `structured+hybrid+soft_v4_frontmatter`
- `soft_v4_frontmatter` keeps dense/fusion as the backbone and adds page-1 front matter role bonuses for title / author / affiliation / abstract / keywords / fact queries.

### Metric Definitions

- `hit@k = 1` if at least one correct result appears within top-k, else `0`.
- `first_correct_rank(case)` is the 1-based rank of the first result that satisfies the case expectation jointly: expected page + expected block type + expected section/keywords when provided.
- `MRR(case) = 1 / first_correct_rank(case)` if a jointly-correct result exists, else `0`.
- `*_top1_accuracy` is the share of cases in that query type whose top-1 result is jointly correct.

## 2. Front Matter Bucket

| Mode | page_hit@1 | page_hit@3 | page_hit@5 | section_hit@1 | section_hit@3 | section_hit@5 | bt_hit@1 | bt_hit@3 | bt_hit@5 | first_correct_rank | MRR |
|------|------------|------------|------------|---------------|---------------|---------------|----------|----------|----------|--------------------|-----|
| Structured+Hybrid | 0.385 | 0.769 | 0.846 | 0.231 | 0.231 | 0.462 | 0.692 | 1.0 | 1.0 | 2.5 | 0.291 |
| Structured+Hybrid+SoftV3 | 0.385 | 0.923 | 1.0 | 0.231 | 0.385 | 0.462 | 0.692 | 1.0 | 1.0 | 2.143 | 0.333 |
| Structured+Hybrid+FrontMatterAware | 1.0 | 1.0 | 1.0 | 0.538 | 0.538 | 0.538 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

### 2a. Query-Type Top1 Accuracy

| Mode | title_top1_accuracy | author_top1_accuracy | affiliation_top1_accuracy | abstract_top1_accuracy | keywords_top1_accuracy |
|------|---------------------|----------------------|---------------------------|------------------------|------------------------|
| Structured+Hybrid | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Structured+Hybrid+SoftV3 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Structured+Hybrid+FrontMatterAware | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

## 3. Control Bucket

| Mode | page_hit@1 | page_hit@5 | section_hit@1 | section_hit@5 | MRR |
|------|------------|------------|---------------|---------------|-----|
| Structured+Hybrid | 0.667 | 1.0 | 0.667 | 1.0 | 0.833 |
| Structured+Hybrid+SoftV3 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| Structured+Hybrid+FrontMatterAware | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

## 4. Per-Case Snapshot

| Case | Bucket | Query Type | Structured+Hybrid | SoftV3 | FrontMatterAware |
|------|--------|------------|-------------------|--------|------------------|
| **title_cn** | front_matter | title_query | top1=0.0 / rank=-1 / mrr=0.0 | top1=0.0 / rank=3 / mrr=0.3333 | top1=1.0 / rank=1 / mrr=1.0 |
| **title_en** | front_matter | title_query | top1=0.0 / rank=-1 / mrr=0.0 | top1=0.0 / rank=-1 / mrr=0.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **author_names** | front_matter | author_query | top1=0.0 / rank=3 / mrr=0.3333 | top1=0.0 / rank=3 / mrr=0.3333 | top1=1.0 / rank=1 / mrr=1.0 |
| **first_author** | front_matter | author_query | top1=0.0 / rank=-1 / mrr=0.0 | top1=0.0 / rank=-1 / mrr=0.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **author_affiliation** | front_matter | affiliation_query | top1=0.0 / rank=-1 / mrr=0.0 | top1=0.0 / rank=-1 / mrr=0.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **first_author_affiliation** | front_matter | affiliation_query | top1=0.0 / rank=-1 / mrr=0.0 | top1=0.0 / rank=-1 / mrr=0.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **abstract_cn** | front_matter | abstract_query | top1=0.0 / rank=4 / mrr=0.25 | top1=0.0 / rank=3 / mrr=0.3333 | top1=1.0 / rank=1 / mrr=1.0 |
| **abstract_en** | front_matter | abstract_query | top1=0.0 / rank=-1 / mrr=0.0 | top1=0.0 / rank=-1 / mrr=0.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **keywords_cn** | front_matter | keywords_query | top1=0.0 / rank=5 / mrr=0.2 | top1=0.0 / rank=3 / mrr=0.3333 | top1=1.0 / rank=1 / mrr=1.0 |
| **keywords_en** | front_matter | keywords_query | top1=0.0 / rank=-1 / mrr=0.0 | top1=0.0 / rank=-1 / mrr=0.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **recv_date** | front_matter | front_matter_fact_query | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **clc_number** | front_matter | front_matter_fact_query | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **funding** | front_matter | front_matter_fact_query | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **fig2_control** | control | figure_query | top1=0.0 / rank=2 / mrr=0.5 | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **table1_control** | control | table_query | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 |
| **sec_1_2_control** | control | section_query | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 | top1=1.0 / rank=1 / mrr=1.0 |

## 5. Representative Query Comparison

### 1. [title_cn] 这篇论文的标题是什么？

*Notes: 中文标题，应命中 page 1 主标题 heading。*

**Structured+Hybrid** (top1_correct=0.0, first_correct_rank=-1, mrr=0.0):

  [1] p4 [heading] role=- section='与已有综述研究的比较以及本文的贡献' score=0.0323 dense=0.6395 lexical=14.5179 fusion=0.0323 text=1.3 与已有综述研究的比较以及本文的贡献...
  [2] p2 [heading] role=- section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.0297 dense=0.6801 lexical=7.2075 fusion=0.0297 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [3] p7 [paragraph] role=- section='模型压缩\n[67]' score=0.0267 dense=0.4094 lexical=8.6225 fusion=0.0267 text=练值得关注. 值得一 提的是在边缘协同推理场景，受限资源的分配及调 度粒度至关重要，该问题将决定“腾出资源做合适的 任务”等资源调度及优化的发展. 除此之外，还需要 注意的是，边缘...

**Structured+Hybrid+SoftV3** (top1_correct=0.0, first_correct_rank=3, mrr=0.3333):

  [1] p4 [heading] role=- section='与已有综述研究的比较以及本文的贡献' score=0.8983 dense=0.6395 lexical=14.5179 fusion=0.0323 text=1.3 与已有综述研究的比较以及本文的贡献...
  [2] p2 [heading] role=- section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.7863 dense=0.6801 lexical=7.2075 fusion=0.0297 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [3] p1 [heading] role=title_cn section='' score=0.6056 dense=0.5971 lexical=2.6793 fusion=0.0156 text=面向边缘智能的协同推理综述...

**Structured+Hybrid+FrontMatterAware** (top1_correct=1.0, first_correct_rank=1, mrr=1.0):

  [1] p1 [heading] role=title_cn section='' score=1.0189 dense=0.5971 lexical=2.6793 fusion=0.0156 text=面向边缘智能的协同推理综述...
  [2] p1 [paragraph] role=author_affiliation section='' score=0.6144 dense=0.4199 lexical=0.0 fusion=0.4199 text=王 睿 1,2 齐建鹏 1 陈 亮 1 杨 龙 1 1 （北京科技大学计算机与通信工程学院 北京 100083） 2 （北京科技大学顺德研究生院 广东佛山 528300） （wan...
  [3] p1 [heading] role=abstract_heading_cn section='Key words edge computing；edge intelligence；machine learning；edge collaborative inference；dynamic scenario' score=0.6038 dense=0.4276 lexical=0.0 fusion=0.4276 text=摘 要...

### 2. [author_affiliation] 作者单位是什么？

*Notes: 作者单位应命中中文作者/单位段落。*

**Structured+Hybrid** (top1_correct=0.0, first_correct_rank=-1, mrr=0.0):

  [1] p7 [paragraph] role=- section='模型压缩\n[67]' score=0.0268 dense=0.404 lexical=3.3426 fusion=0.0268 text=练值得关注. 值得一 提的是在边缘协同推理场景，受限资源的分配及调 度粒度至关重要，该问题将决定“腾出资源做合适的 任务”等资源调度及优化的发展. 除此之外，还需要 注意的是，边缘...
  [2] p1 [heading] role=title_cn section='' score=0.0252 dense=0.5892 lexical=0.0 fusion=0.0252 text=面向边缘智能的协同推理综述...
  [3] p8 [caption] role=- section='整体架构' score=0.0164 dense=0.673 lexical=0.0 fusion=0.0164 text=图 6 模型选择模式...

**Structured+Hybrid+SoftV3** (top1_correct=0.0, first_correct_rank=-1, mrr=0.0):

  [1] p7 [paragraph] role=- section='模型压缩\n[67]' score=0.7218 dense=0.404 lexical=3.3426 fusion=0.0268 text=练值得关注. 值得一 提的是在边缘协同推理场景，受限资源的分配及调 度粒度至关重要，该问题将决定“腾出资源做合适的 任务”等资源调度及优化的发展. 除此之外，还需要 注意的是，边缘...
  [2] p1 [heading] role=title_cn section='' score=0.6936 dense=0.5892 lexical=0.0 fusion=0.0252 text=面向边缘智能的协同推理综述...
  [3] p1 [heading] role=abstract_heading_cn section='Key words edge computing；edge intelligence；machine learning；edge collaborative inference；dynamic scenario' score=0.4264 dense=0.6578 lexical=0.0 fusion=0.0159 text=摘 要...

**Structured+Hybrid+FrontMatterAware** (top1_correct=1.0, first_correct_rank=1, mrr=1.0):

  [1] p1 [paragraph] role=author_affiliation section='' score=1.1512 dense=0.3518 lexical=0.0 fusion=0.3518 text=王 睿 1,2 齐建鹏 1 陈 亮 1 杨 龙 1 1 （北京科技大学计算机与通信工程学院 北京 100083） 2 （北京科技大学顺德研究生院 广东佛山 528300） （wan...
  [2] p1 [paragraph] role=author_affiliation section='' score=0.7781 dense=0.077 lexical=0.0 fusion=0.077 text=Wang Rui1,2 , Qi Jianpeng1 , Chen Liang1 , and Yang Long1 1  （School of Computer and Commu...
  [3] p1 [heading] role=fact_recv section='关键词 边缘计算；边缘智能；机器学习；边缘协同推理；动态场景' score=0.5764 dense=0.4146 lexical=0.0 fusion=0.4146 text=收稿日期：2021−08−26；修回日期：2022−04−15...

### 3. [abstract_cn] 摘要讲了什么？

*Notes: 中文摘要应优先命中摘要正文 paragraph，而不是“摘 要” heading。*

**Structured+Hybrid** (top1_correct=0.0, first_correct_rank=4, mrr=0.25):

  [1] p1 [heading] role=abstract_heading_cn section='Key words edge computing；edge intelligence；machine learning；edge collaborative inference；dynamic scenario' score=0.0328 dense=0.6821 lexical=19.5073 fusion=0.0328 text=摘 要...
  [2] p7 [paragraph] role=- section='模型压缩\n[67]' score=0.0245 dense=0.3965 lexical=2.516 fusion=0.0245 text=练值得关注. 值得一 提的是在边缘协同推理场景，受限资源的分配及调 度粒度至关重要，该问题将决定“腾出资源做合适的 任务”等资源调度及优化的发展. 除此之外，还需要 注意的是，边缘...
  [3] p8 [caption] role=- section='整体架构' score=0.0161 dense=0.6567 lexical=0.0 fusion=0.0161 text=图 6 模型选择模式...

**Structured+Hybrid+SoftV3** (top1_correct=0.0, first_correct_rank=3, mrr=0.3333):

  [1] p1 [heading] role=abstract_heading_cn section='Key words edge computing；edge intelligence；machine learning；edge collaborative inference；dynamic scenario' score=0.9873 dense=0.6821 lexical=19.5073 fusion=0.0328 text=摘 要...
  [2] p7 [paragraph] role=- section='模型压缩\n[67]' score=0.4525 dense=0.3965 lexical=2.516 fusion=0.0245 text=练值得关注. 值得一 提的是在边缘协同推理场景，受限资源的分配及调 度粒度至关重要，该问题将决定“腾出资源做合适的 任务”等资源调度及优化的发展. 除此之外，还需要 注意的是，边缘...
  [3] p1 [paragraph] role=abstract_body_cn section='摘 要' score=0.3504 dense=0.2105 lexical=5.9564 fusion=0.0161 text=近年来，信息技术的不断变革伴随数据量的急剧爆发，使主流的云计算解决方案面临实时性差、 带宽受限、高能耗、维护费用高、隐私安全等问题. 边缘智能的出现与快速发展有效缓解了此类问题，它...

**Structured+Hybrid+FrontMatterAware** (top1_correct=1.0, first_correct_rank=1, mrr=1.0):

  [1] p1 [paragraph] role=abstract_body_cn section='摘 要' score=0.9472 dense=0.2105 lexical=5.9564 fusion=0.0161 text=近年来，信息技术的不断变革伴随数据量的急剧爆发，使主流的云计算解决方案面临实时性差、 带宽受限、高能耗、维护费用高、隐私安全等问题. 边缘智能的出现与快速发展有效缓解了此类问题，它...
  [2] p1 [heading] role=abstract_heading_cn section='Key words edge computing；edge intelligence；machine learning；edge collaborative inference；dynamic scenario' score=0.5957 dense=0.6821 lexical=19.5073 fusion=0.0328 text=摘 要...
  [3] p1 [paragraph] role=abstract_body_en section='Abstract' score=0.58 dense=-0.0699 lexical=0.0 fusion=-0.0699 text=At present, the continuous change of information technology along with the dramatic explos...

### 4. [keywords_cn] 关键词有哪些？

*Notes: 中文关键词在当前结构化结果中是 heading 块。*

**Structured+Hybrid** (top1_correct=0.0, first_correct_rank=5, mrr=0.2):

  [1] p2 [caption] role=- section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.031 dense=0.5537 lexical=18.6841 fusion=0.031 text=图 1 边缘智能发展趋势...
  [2] p2 [heading] role=- section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.0299 dense=0.507 lexical=22.0816 fusion=0.0299 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [3] p3 [caption] role=- section='边缘协同推理的整体过程' score=0.0296 dense=0.5492 lexical=9.7551 fusion=0.0296 text=图 2 协同推理关键技术出现时间...

**Structured+Hybrid+SoftV3** (top1_correct=0.0, first_correct_rank=3, mrr=0.3333):

  [1] p2 [caption] role=- section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.9489 dense=0.5537 lexical=18.6841 fusion=0.031 text=图 1 边缘智能发展趋势...
  [2] p2 [heading] role=- section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.9087 dense=0.507 lexical=22.0816 fusion=0.0299 text=关键词进行检索，得到的关于边缘智能的文献数量...
  [3] p1 [heading] role=keywords_cn section='关键词 边缘计算；边缘智能；机器学习；边缘协同推理；动态场景' score=0.882 dense=0.4038 lexical=20.6059 fusion=0.0282 text=关键词 边缘计算；边缘智能；机器学习；边缘协同推理；动态场景...

**Structured+Hybrid+FrontMatterAware** (top1_correct=1.0, first_correct_rank=1, mrr=1.0):

  [1] p1 [heading] role=keywords_cn section='关键词 边缘计算；边缘智能；机器学习；边缘协同推理；动态场景' score=1.0182 dense=0.4038 lexical=20.6059 fusion=0.0282 text=关键词 边缘计算；边缘智能；机器学习；边缘协同推理；动态场景...
  [2] p1 [paragraph] role=author_affiliation section='' score=0.5777 dense=0.2875 lexical=0.0 fusion=0.2875 text=王 睿 1,2 齐建鹏 1 陈 亮 1 杨 龙 1 1 （北京科技大学计算机与通信工程学院 北京 100083） 2 （北京科技大学顺德研究生院 广东佛山 528300） （wan...
  [3] p2 [heading] role=- section='关键词进行检索，得到的关于边缘智能的文献数量' score=0.4828 dense=0.507 lexical=22.0816 fusion=0.0299 text=关键词进行检索，得到的关于边缘智能的文献数量...

### 5. [fig2_control] 图 2 反映了什么内容？

*Notes: control case，用于确认 front matter rerank 不伤害 figure caption 查询。*

**Structured+Hybrid** (top1_correct=0.0, first_correct_rank=2, mrr=0.5):

  [1] p4 [caption] role=- section='模型切割' score=0.0325 dense=0.6687 lexical=8.374 fusion=0.0325 text=图4 所示，按照模型的内部结构可通过纵切、横切及...
  [2] p3 [caption] role=- section='边缘协同推理的整体过程' score=0.0325 dense=0.6029 lexical=10.2783 fusion=0.0325 text=图 2 协同推理关键技术出现时间...
  [3] p5 [caption] role=- section='模型切割' score=0.0294 dense=0.5298 lexical=4.316 fusion=0.0294 text=图 4 模型切割方式...

**Structured+Hybrid+SoftV3** (top1_correct=1.0, first_correct_rank=1, mrr=1.0):

  [1] p3 [caption] role=- section='边缘协同推理的整体过程' score=1.1814 dense=0.6029 lexical=10.2783 fusion=0.0325 text=图 2 协同推理关键技术出现时间...
  [2] p4 [caption] role=- section='模型切割' score=1.014 dense=0.6687 lexical=8.374 fusion=0.0325 text=图4 所示，按照模型的内部结构可通过纵切、横切及...
  [3] p5 [caption] role=- section='模型切割' score=0.8152 dense=0.5298 lexical=4.316 fusion=0.0294 text=图 4 模型切割方式...

**Structured+Hybrid+FrontMatterAware** (top1_correct=1.0, first_correct_rank=1, mrr=1.0):

  [1] p3 [caption] role=- section='边缘协同推理的整体过程' score=1.1814 dense=0.6029 lexical=10.2783 fusion=0.0325 text=图 2 协同推理关键技术出现时间...
  [2] p4 [caption] role=- section='模型切割' score=1.014 dense=0.6687 lexical=8.374 fusion=0.0325 text=图4 所示，按照模型的内部结构可通过纵切、横切及...
  [3] p5 [caption] role=- section='模型切割' score=0.8152 dense=0.5298 lexical=4.316 fusion=0.0294 text=图 4 模型切割方式...

## 6. Conclusions

- Front matter delta: page_hit@1 1.0 vs 0.385; section_hit@1 0.538 vs 0.231; MRR(case) 1.0 vs 0.333.
- Top1 accuracy delta: title 1.0 vs 0.0; author 1.0 vs 0.0; affiliation 1.0 vs 0.0; abstract 1.0 vs 0.0; keywords 1.0 vs 0.0.
- Control delta: page_hit@1 1.0 vs 1.0; page_hit@5 1.0 vs 1.0; section_hit@5 1.0 vs 1.0; MRR(case) 1.0 vs 1.0.
- Interpretation: this v5 report isolates page-1 front matter ranking bias; structured chunking and generic hybrid retrieval remain unchanged.

## 7. Scope and Limitations

- Scope: this is a **single-document experiment** on `05_crad_10.7544_issn1000-1239.202110867.pdf`, not a cross-paper benchmark.
- Sample size: **13** front matter cases + **3** control cases. Results are useful for targeted diagnosis, but the sample is still small.
- Fact-query note: `recv_date`, `clc_number`, and `funding` already achieve top-1 correctness under the base hybrid setting in this report. For these cases, v5 mainly shows **no regression**, not a large additional gain.
- Control-bucket note: the control bucket only contains figure / table / section probes. With only 3 cases, the current evidence supports **no observed regression** rather than a strong general claim of no harm.
- Front-matter heuristic note: the current English-title detection uses a small page-1 order prior (`chunk_idx <= 4`). It works for this PDF, but front matter ordering may differ in other papers and should be validated before generalization.
