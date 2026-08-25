# PRD 产品需求文档（PRD）
**项目名称**：MindDock 可验证文献工作台（Verifiable Literature Workbench）
**版本**：v1.1
**日期**：2026-08-25
**文档状态**：已评审定稿（v1.0，产品经理提案 × 技术总监代码级评审）；v1.1 同步首轮实现状态
**前置文档**：`docs/SRS_个人知识管理助手_v1.0.md`、`docs/ROADMAP.md`、`docs/thesis-alignment.md`

## 修订记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-08-25 | 双 agent（PM × CTO）评审定稿：定位、P0 范围、修正后排期、Non-goals、决策纪要 |
| v1.1 | 2026-08-25 | 同步首轮实现状态（FR-1/2/3/4/6/9 完成，FR-3b 移植完成待回归开启）；FR-9 提前交付；附录 B 开放问题部分关闭；新增第 13 节实现状态与偏差记录 |

---

## 0. 摘要

本 PRD 定义 MindDock 下一周期（90 天）的产品方向：**给研究者的"可验证文献工作台"**。

差异化主张：**答案敢自证**——不只是"答案带引用"（NotebookLM 及开源平替均已具备），而是每个答案附带证据充分度评分、逐条引用自检报告与可复现的检索参数，形成"唯一一个敢给答案打分的知识库"的产品认知。

核心结论（双 agent 讨论决议）：
1. 五项 P0/P0 级前置功能全部复用现有后端资产的可复用部分，按**依赖顺序**重排：评测集扩容 → 证据充分度徽章 + 引用自检报告 → 学术元数据抽取与过滤 → 引用格式导出 → frontmatter ranking 生产化移植 → 综述工作台。
2. 三处 PM 高估复用度之处已修正：frontmatter ranking 仅存在于实验脚本（`scripts/eval_chunking.py:723-819`），从未进入生产管线；作者/年份元数据从未持久化进 Chroma（`app/rag/ingest.py:138-165`）；"答案内逐句引用锚点"不存在（`inline_ref` 是序列化后置序号，`app/application/artifacts.py:254`）。
3. 所有对外指标承诺在评测集扩至 ≥50 例后再行定标，当前 n=10 的指标不做对外承诺。

---

## 1. 背景与定位

### 1.1 竞品格局（2026）

| 竞品 | 优势 | 与本产品的关系 |
|---|---|---|
| Google NotebookLM | 云端免费、播客/闪卡/导图，定义品类预期 | 黑盒不可验证，无法核验答案——正是本产品要打的点 |
| KnowNote / Open Notebook | 双击安装 / Docker 一键、格式覆盖广 | 在部署与内容玩法上竞争，本产品不跟进 |
| AnythingLLM / Cherry Studio | 开箱即用、格式聚合 | 通用工具，无证据自证能力 |
| Jarvis / 4DPocket | 本地记忆 + MCP server | 生态方向参考，MCP 列入 P2 POC |

### 1.2 定位

> **MindDock = 给研究者的可验证文献工作台**
> 每个答案都带证据充分度评分与引用自检报告——不只是给答案，而是敢给答案打分。

### 1.3 已验证的技术资产（差异化根基）

- 评测体系：hit@k、引用一致性基线（`app/evaluation/`），全行业罕见的产品化潜力
- frontmatter-aware ranking：论文标题/作者/摘要查询 top1 从 0% → 100%（`eval/chunking_eval_report_v5.md`）
- Workflow Trace + Prompt Profile 版本化：可审计的答案生成过程
- 检索质量信号：`support_status` 四态枚举、`quality_ok` / `low_confidence` 已随响应下发

---

## 2. 目标用户与核心场景

**主画像：林潇，计算机专业研二学生**。知识库 50–200 篇 PDF + 网页剪藏，正在写 Related Work。痛点：NotebookLM 类工具给答案但无法核验，不敢直接写进论文；引用格式靠手工补，经常对不上原文。

**关键用户旅程**：
1. **问答核验**：提问 → 看到黄色徽章（证据支撑一般）→ 展开自检报告发现 1 条引用与结论不一致 → 点击引用定位原文 → 调整过滤条件重新提问。
2. **综述写作**：按作者/年份过滤检索 → compare 多种方法 → 逐条核对 citation → 一键导出 GB/T 7714 引用贴进论文。
3. **答辩质询**：导师问"这个结论哪来的"→ 打开 Workflow Trace + 自检报告，30 秒内给出证据链。

---

## 3. 产品目标

| 编号 | 目标 | 度量 | 定标时点 |
|---|---|---|---|
| G1 | "可验证"成为可感知的产品能力 | chat / summarize 输出 100% 携带徽章与自检报告；自检判定与人工抽检一致率 ≥ 85% | 50 例评测集落地后 |
| G2 | 答辩级实验结果转化为产品质量 | 评测集 ≥ 50 例；hit@1 与来源一致率提升幅度在 50 例集上量化承诺（原 50% / 57% 基线） | 50 例评测集落地后 |
| G3 | 验证研究者真实价值 | ≥ 10 名研究生/科研人员试用；第 4 周周活留存 ≥ 40%；引用导出累计使用 ≥ 200 次 | 试用期内 |

> ⚠️ 决议：G2 的具体数值目标（如 hit@1 ≥ 65%）顺延至 M3 验收时基于 50 例集重新承诺。当前 10 例样本（其中 7 例有期望来源标注）不具备统计效力。

---

## 4. 需求范围总览

### 4.1 依赖顺序（技术评审修正后）

```text
评测集扩容(FR-5)
  → 证据徽章 v1(FR-1) + 引用自检 MVP(FR-2)        [并行]
  → 学术元数据抽取与过滤(FR-3)
  → 引用格式导出(FR-4)                             [依赖 FR-3 元数据入库]
  → frontmatter ranking 生产化移植(FR-3b)
  → compare 质量信号补齐(FR-6) → 综述工作台(FR-7)
```

### 4.2 优先级总表

| 编号 | 功能 | 优先级 | 复用度（评审修正后） | 工作量 |
|---|---|---|---|---|
| FR-5 | 评测集扩容至 ≥50 例 + CI 接入 | **P0（前置）** | 基本直接复用 runner/metrics/reporting | S |
| FR-1 | 证据充分度徽章 | P0 | 部分复用（信号整答案级；compare 缺失） | S–M |
| FR-2 | 引用自检报告 | P0 | 部分复用（结构复用；三态判定需新建） | M |
| FR-3 | 学术元数据抽取 + 过滤 | P0 | 过滤扩展 S 级；元数据抽取入库需新建 + 全库 re-ingest | M |
| FR-4 | 引用格式导出（BibTeX / GB/T 7714 / APA） | P0 | 格式化器 S 级；**依赖 FR-3** | S |
| FR-3b | frontmatter ranking 生产化移植 | P0 | **实验脚本移植 + 重实现（非配置开关）** | L |
| FR-6 | compare 质量信号补齐 | P1 | 新建（compare 走内部检索，无统一管线信号） | S |
| FR-7 | 综述工作台（简版） | P1 | 部分复用 compare+summarize；多文档聚合新建 | M |
| FR-8 | MCP 只读工具 POC | P2 | 新建（验证生态假设，不做写入） | M |
| FR-9 | .ics 日程导出 | P2 | 新建 | S |

---

## 5. 功能需求详述

### FR-1 证据充分度徽章

- **用户故事**：As a 研究者，I want 在读答案前一眼看到证据支撑强度，So that 决定是否需要逐条核验。
- **描述**：答案顶部显示绿/黄/红徽章；悬停展示构成（support_status、低置信标记、trace warnings）；与现有"引用严格度"偏好联动。
- **映射规则（v1，确定性映射，与现有枚举一一对应）**：
  - 绿 = `support_status=supported` 且无 `low_confidence` 且无 trace warnings
  - 黄 = `partial` 或存在 `low_confidence`
  - 红 = `insufficient_evidence` 或检索空
  - compare 任务在 FR-6 完成前显示"未知"
- **验收标准**：
  1. Given 知识库含相关文档，When chat 检索充分（supported、无低置信），Then 徽章为绿；
  2. When low_confidence 或 partial，Then 黄/红且附建议（放宽过滤/补充关键词）；
  3. M1 上线时**先埋点记录不上显**，50 例评测集定标后于 M2 打开显示。
- **技术要点**：信号源 `app/rag/retrieval_models.py:143-149`（support_status）、`app/workflows/unified_pipeline.py:206-246`（quality_ok/low_confidence）、`app/services/workflow_trace.py:90-114`（trace_warnings）；前端挂载点为现有 "Why this answer?" 面板（`frontend/src/features/agent/components/agent-message-list.tsx:154-214`）。
- **不做**：不采用"hit≥3→绿"类数值阈值（无定标数据）；不改生成端 prompt。

### FR-2 引用自检报告

- **用户故事**：As a 研究者，I want 系统自动回验每条引用是否真支持对应结论，So that 不必逐条人工比对原文。
- **描述**：答案生成后自动运行"结论-引用"一致性回验，输出报告（每条引用：支持 / 部分支持 / 不支持 + 理由）；判定不支持的引用在 **citation list 中标灰**；报告随 run 写入 Workflow Trace 并**落盘持久化**（跨会话可回看）。
- **架构决议（双层判定）**：
  - **规则层（同步，零成本）**：引用结构有效性 + 证据对齐度，复用 `evaluate_citation_consistency` 思路（`app/evaluation/metrics.py:157-203`）与 `assess_evidence_query_alignment`（`app/services/grounded_generation.py:266-347`）；
  - **LLM 回验层（异步 SSE）**：逐引用 NLI 三态判定，作为答案 artifact 之后的独立事件发出（基础设施 `app/api/routes.py:327-448`、`app/application/run_control.py:129-151`），用户感知延迟 ≈ 0；引用数被压缩器硬顶 4 条（`app/rag/postprocess.py:18`），单次批量调用成本可控。
- **验收标准**：
  1. Given 含 3 条引用的答案，When 自检完成，Then 报告逐条给出三态判定且可点击跳转对应 chunk；
  2. When 某引用判定不支持，Then citation list 对应项标灰并提示；
  3. 自检报告写入磁盘，重启后端后仍可查看（trace 落盘，替代当前 RunRegistry 内存态 + TTL 方案，`app/application/run_control.py:179`）；
  4. 自检附加可感知延迟 ≤ 3s（异步事件在答案后 10s 内呈现）；
  5. 自检判定与人工抽检一致率 ≥ 85%（50 例集上度量）。
- **明确降级（决议）**：MVP 不做"答案文本内逐句标灰"——生产 prompt 的引用策略是"citations derived from evidence chunks"（`app/prompts/registry.py:173`），`inline_ref` 为序列化后置序号（`app/application/artifacts.py:254`），不存在逐句锚点；句子级 claim 匹配由自检模块自行切分实现，不动生成端基线。
- **与评测的关系**：线上自检（运行时 LLM 判定）与评测（golden-label 规则判定）共用 case schema 与报告器（`app/evaluation/runner.py:57-81`），判定逻辑各自独立模块。

### FR-3 学术元数据抽取与过滤（含 FR-3b ranking 移植）

- **用户故事**：As a 研究者，I want 按作者/年份/标题过滤检索，So that 在大文献库中快速收敛范围。
- **描述（FR-3 主线：抽取 + 过滤）**：
  1. ingest 时抽取论文 frontmatter 元数据（作者、年份、venue、DOI），持久化进 Chroma chunk metadata；作者块识别以 `_looks_like_author_or_affiliation_block`（`app/rag/structured_chunker.py:539-560`）为起点；
  2. filter model 新增 `author` / `year` 过滤：`MetadataFilters`（`app/api/schemas.py:97-150`）→ `RetrievalFilters`（`app/rag/retrieval_models.py:12-61`）→ `_build_where` / `_apply_post_filters`（`app/rag/vectorstore.py:472-525`），改动约 5 个文件；
  3. **过滤实现决议**：author/year 先经元数据预查询解析为 doc_id 集合（`_build_where` 扩展 `$in`），再做检索——避免纯后过滤在高选择性场景（200 篇中 1 位作者）下的假"无结果"召回风险；
  4. 提供全库 re-ingest 脚本（旧 chunk 无新字段，直接过滤会静默空结果）。
- **描述（FR-3b：ranking 生产化移植）**：将 `soft_rerank_v4_frontmatter`（`scripts/eval_chunking.py:723-819`）移植进生产 `HeuristicReranker`（`app/rag/postprocess.py:132-172`）。**注意：这不是"固化开关"，实验脚本自带 dense/lexical/fusion 候选管线，与生产 `SearchService` 非同一代码路径，属移植 + 重实现。**
- **验收标准**：
  1. Given 已入库文献，When 过滤"作者=X AND 年份=2021"，Then 结果仅含命中文档且 P95 延迟无显著劣化（生成段主导）；
  2. When 元数据缺失，Then 过滤项明示"未抽取到该字段"，不静默返回空；
  3. FR-3b：先跑 `eval/eval_cases_front_matter_multi.json`（已存在 13 例、2 篇 PDF、**从未出报告**）出基线 → 移植 → 复跑多文档集与 10 例基准双回归，top1 ≥ 85% 且 control 用例无回退。
- **泛化风险（已知失败模式）**：英文 arXiv 风格"标题+作者合并单块"导致角色识别失效（multi 集案例备注）；`chunk_idx<=4` 页 1 顺序先验是版式相关；中文期刊锚词（收稿日期/中图法分类号）对英文文献无效。**决议：先泛化验证再上线。**

### FR-4 学术引用格式导出

- **用户故事**：As a 论文写作者，I want 从检索/对比结果一键导出规范引用格式，So that 直接贴进论文且不引错。
- **描述**：Source 详情与 chat/compare 引用卡片提供 BibTeX / GB/T 7714 / APA 导出（复制 + .bib 文件）；元数据取自 FR-3 入库的 frontmatter 字段，缺失字段自动降级并标注。
- **依赖决议**：**FR-3 元数据抽取先行，FR-4 随后**。若顺序颠倒，导出将以降级条目为主（当前 Chroma metadata 无 author/year/journal/DOI，`app/rag/ingest.py:138-165`）。
- **验收标准**：
  1. Given 含完整 frontmatter 的 PDF 已 re-ingest，When 导出 GB/T 7714，Then 输出含作者/题名/年份/页码且通过格式校验；
  2. When 元数据缺失，Then 对应导出项置灰并提示补全入口；
  3. 导出格式人工校验通过率 100%（试用期度量）。

### FR-5 评测集扩容与 CI 接入（前置任务）

- **描述**：评测集从 10 例扩至 ≥ 50 例（覆盖多文档/多类型/frontmatter/英文文献查询），接入现有 CI baseline（`scripts/run_ci_baseline.py`），每次发版自动产出评测报告；为 FR-1 徽章阈值定标与 G2 指标承诺提供数据。
- **验收标准**：50 例集产出基线报告；CI 发版流程自动运行；徽章三档分布报告可用于定标。
- **工作量**：技术侧 S 级（runner/metrics/reporting 全链路在产），案例编写为持续性工作。

### FR-6 compare 质量信号补齐（P1）

- **背景（评审发现）**：compare 走内部检索、`precomputed_hits=None`（`app/application/orchestrators.py:1228`），无 quality_check、无低置信警告、无 trace 合并——是质量信号盲区。
- **描述**：compare 接入统一管线或独立补 quality_check，使徽章/自检在 compare 输出上生效。
- **定位**：**FR-7 综述工作台的前置任务**（综述建立在 compare 之上，不补信号则徽章在新功能上集体缺席）。

### FR-7 综述工作台（简版，P1）

- **用户故事**：As a 综述写作者，I want 自动生成 Related Work 对比表（方法/数据集/结论/引用），So that 加速初稿。
- **描述**：复用 compare + summarize，指定 3–5 篇文档，输出对比表且每格带可点击引用；多文档聚合为新建逻辑（当前 compare 为 pairwise，>2 source 截断为前两个）。
- **验收标准**：Given 3–5 篇指定文档，When 运行综述，Then 输出对比表，每格引用可点击跳转，徽章/自检报告生效（依赖 FR-6）。

### P2（本周期按余力，不做承诺）

- **FR-8 MCP 只读工具 POC**：暴露 /search 为只读 MCP tool 供 Claude Desktop / Cursor 调用，验证生态分发假设；不做写入。
- **FR-9 .ics 导出**：日程候选闭环的最低成本补全。
- **部署体验**：以 `uv sync && uv run minddock`（现有 `python -m app.demo` 链路）+ README 替代"一条命令启动"（原 P1-2 降级：无 `[project.scripts]` 入口、前端无静态托管、sentence-transformers/torch 重依赖使 pip install 体验先天不良）。

---

## 6. Non-goals（明确不做）

1. 多租户、云端托管与账号体系（维持本地优先，与 ROADMAP 一致）。
2. 通用聊天机器人与自主 Agent 控制器。
3. 插件市场、远程 Skill 安装、签名校验与沙箱。
4. Word/Docx 导入、JS 渲染网页抓取（下一周期再议）。
5. 长期用户记忆与用户画像（维持 workspace-local 偏好定位）。
6. 生产级日历双向同步。
7. 答案文本内逐句引用标灰（需 prompt 改造与基线重评，移至后续周期）。

---

## 7. 非功能需求

| 编号 | 需求 |
|---|---|
| NFR-1 | 自检报告 LLM 层异步 SSE，答案主链路 P95 不劣化（现 chat P95 9.63s，同步回验会推至 12s+，不可接受） |
| NFR-2 | 自检报告与 Workflow Trace 落盘持久化，支持跨会话/重启后回看 |
| NFR-3 | 新增元数据字段配套 re-ingest 脚本与向后兼容策略（旧库过滤不静默返回空） |
| NFR-4 | 徽章映射为确定性规则（枚举一一对应），不引入无定标数据的数值阈值 |
| NFR-5 | LLM 回验失败时降级为规则层结果，不阻塞答案呈现 |
| NFR-6 | 评测基线纳入 CI，任何检索端改动（ranking 移植、过滤扩展）必须双回归（多文档集 + 10 例基准） |

---

## 8. 里程碑与排期（评审修正后）

团队假设：1 名后端全职当量 + 1 名前端兼职。

| 阶段 | 时间 | 交付 | 出口标准 |
|---|---|---|---|
| **M1 信任内核** | D1–30 | FR-5 评测集 50 例（最先落地）；FR-1 徽章 v1（确定性映射，先埋点后展示）；FR-2 自检 MVP（规则层同步 + LLM 层异步 SSE + citation 标灰 + trace 落盘） | 全部 chat 输出带徽章信号；自检报告可跨会话回放；50 例基线报告产出 |
| **M2 工作台成形** | D31–60 | FR-3 元数据抽取 + 过滤（含 re-ingest 脚本）；FR-4 引用导出；徽章经 50 例定标后打开显示 | FR-2/3/4 全量验收通过；导出格式人工校验通过率 100% |
| **M3 检索攻坚与验证** | D61–90 | FR-3b ranking 移植与双回归（M2 不做，避免 L 级叠加）；FR-6 compare 信号；FR-7 综述工作台简版；10+ 人试用；G2 指标基于 50 例集重新承诺并验收 | G1/G3 达成；G2 新承诺达标；产出下一周期决策文档（MCP 是否转正） |

> 排期决议（相对 PM 原案的调整）：
> 1. 原 M2 的 ranking 移植移至 M3（L 级工作 + 全库 re-ingest 叠加在 M2 不可行）；
> 2. 原 P1-2"一条命令启动"降级为 P2；
> 3. hit@1 ≥ 65% 等指标承诺顺延至 M3（依赖 50 例集定标）。

---

## 9. 成功指标与埋点

| 指标 | 目标 | 度量方式 |
|---|---|---|
| 自检判定与人工一致率 | ≥ 85% | 50 例评测集 + 试用期人工抽检 |
| 徽章三档与人工判定一致率 | ≥ 85% | 50 例集定标报告 |
| 红色徽章后的追问率 | ≥ 30% | 前端埋点（衡量引导有效性） |
| 引用导出累计使用 | ≥ 200 次 | 前端埋点 |
| 试用周活留存（第 4 周） | ≥ 40% | 试用 cohort |
| 评测集规模 | ≥ 50 例，CI 自动运行 | 发版流程 |

---

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 徽章假警报（来源一致率 57% 是检索问题，徽章不应替检索背锅） | 徽章 v1 只绑定 support_status / low_confidence / trace_warnings 等语义清晰信号；先埋点后展示 |
| frontmatter ranking 多文档/英文文献泛化失败 | 先跑已存在的 multi 集（13 例）出基线再移植；失败模式已知（英文合并块、版式先验、中文锚词） |
| 实验脚本与生产管线是两套代码，移植后需全部重验 | 移植纳入 M3 专项 + 双回归护栏（NFR-6） |
| 新元数据字段要求全库 re-ingest，旧库兼容 | 配套脚本 + "未抽取到字段"明示，不静默空结果 |
| 自检 LLM 回验成本/延迟 | 引用硬顶 4 条、批量单次调用、异步 SSE、失败降级规则层 |
| n=10 指标噪声经不起答辩追问 | 所有对外指标在 50 例集后承诺（本文档多处强调） |

---

## 11. 附录 A：双 agent 讨论纪要（关键分歧与决议）

| # | PM 立场 | CTO 评审意见（代码证据） | 决议 |
|---|---|---|---|
| 1 | P0-3 导出与 P0-4 过滤相互独立 | 元数据从未入库（`ingest.py:138-165` 无 author/year），导出依赖过滤先行 | 依赖顺序：FR-3 → FR-4 |
| 2 | P0-2 含"答案内引用标灰" | 逐句锚点不存在（`inline_ref` 为后置序号，`artifacts.py:254`；prompt 策略 `registry.py:173`） | MVP 降级为 citation list 标灰 |
| 3 | M2 完成 ranking 产品化 | 实验脚本与生产管线两套代码，是 L 级移植重实现 | 移至 M3，M2 聚焦元数据+导出 |
| 4 | 徽章阈值 hit≥3→绿 | 无定标数据（评测集仅 10 例） | 确定性枚举映射；先埋点后展示 |
| 5 | P1-2 一条命令启动 | 无 console_scripts、无静态托管、重依赖拖累 | 降级 P2，以 uv + README 替代 |
| 6 | 综述工作台直接复用 compare | compare 是质量信号盲区（`orchestrators.py:1228`） | FR-6 补信号作为前置 |
| 7 | 自检同步执行 | chat P95 9.63s，同步回验推至 12s+ | 规则层同步 + LLM 层异步 SSE |
| 8 | Workflow Trace 可回放 | RunRegistry 内存态 + TTL（`run_control.py:179`），非持久化 | trace 落盘纳入 FR-2 验收 |

## 12. 附录 B：遗留开放问题（v1.1 状态标注）

1. ~~trace 落盘的存储格式与容量管理~~ → **已解决**：`data/run_traces/{run_id}.json` 单文件 per run（`app/application/run_trace_archive.py`），best-effort 原子写。容量保留策略（过期清理）**仍开放**。
2. LLM 回验层的 prompt 归属：是否纳入 Prompt Profile Registry 版本化管理 → **仍开放**（当前 prompt 硬编码于 `citation_self_check.py`，未版本化）。
3. FR-3 元数据抽取对非论文 PDF 的降级行为 → **部分解决**：抽取器保守省略（无匹配不写字段），媒体/CSV/URL 源显式排除；但书籍/长网页的误抽取率未实测，**需 50 例集补充非论文样本**。
4. MCP POC（FR-8）若转正，与 Source Skill 控制面的边界关系 → **仍开放**（未开工）。
5. 试用用户招募渠道与数据回收方式（G3 度量落地）→ **仍开放**（未开工）。
6. （新增）FR-3 authors 过滤采用"膨胀候选+后过滤"，高选择性场景（200 篇中 1 位作者）的召回风险仍在；CTO 建议的 doc_id 预解析 `$in` 方案未实施，作为后续优化。

---

## 13. 附录 C：实现状态同步（v1.1，2026-08-25）

首轮开发共 11 个 commit（基线 `20a164b` → `00c9010`），新增 92 个单元测试全部通过；全量回归与基线失败集合完全一致（20/27 个失败为开发环境缺 chromadb 的存量问题，零新增回归）。

| 编号 | 状态 | Commit | 剩余事项 / 偏差记录 |
|---|---|---|---|
| FR-1 证据徽章 | ✅ 完成（后端+前端） | `91ddee8` | 偏差（正向）：compare 因 FR-6 同期交付而直接全量映射，未经历"unknown 过渡期"。阈值定标仍待 50 例集（当前为枚举确定性映射） |
| FR-2 引用自检 | ✅ MVP 完成 | `f8ab85c` | 偏差：LLM 层为 run 内顺序执行、事件在 artifact 之后下发（感知延迟≈0，满足"答案后 10s 呈现"），非真异步线程；"答案内逐句标灰"按决议不做 |
| FR-2 trace 落盘 | ✅ 完成 | `f8ab85c` | `GET /frontend/traces[/{run_id}]` 已可用；过期清理策略未做（附录 B#1） |
| FR-3 元数据+过滤 | ✅ 完成 | `ffbb3f6` | authors 走后过滤（附录 B#6 已知限制）；存量库需 re-ingest 才有 `doc_authors`/`doc_year` |
| FR-4 引用导出 | ✅ 完成（后端+前端复制按钮） | `72e9ce6` | 未做按 doc_id 回查富化，依赖前端传入字段（title/source/page），authors/year 需 re-ingest 后才有 |
| FR-6 compare 信号 | ✅ 完成 | `a9f4b1c` | 无 |
| FR-3b ranking 移植 | 🟡 移植完成，**flag 默认关闭** | `95bdfd6` | `frontmatter_rerank_enabled=false`；开启前置条件：联网环境跑 `eval_cases_front_matter_multi.json`（13 例）出基线 + 10 例基准双回归（维持 v1.0 决议） |
| FR-9 .ics 导出 | ✅ **提前完成**（原 P2） | `c13736a` | RFC 5545 合规，status 过滤 confirmed/pending/dismissed/all |
| FR-5 评测集扩容 50 例 | ⏳ 未开工 | — | **阻塞 G2 指标承诺**；需真实语料与人工标注，属持续性工作 |
| FR-7 综述工作台 | ⏳ 未开工 | — | M3 余力项 |
| FR-8 MCP POC | ⏳ 未开工 | — | P2，与 Source Skill 边界问题联动（附录 B#4） |

### 里程碑实际进展（对照第 8 节）

- **M1（信任内核）**：FR-5 之外全部达成（徽章、自检 MVP、trace 落盘均可用）；评测集扩容顺延为 M2 首项。
- **M2（工作台成形）**：FR-3/FR-4 已提前完成；剩余为徽章定标展示（依赖 50 例集）与评测扩容。
- **M3（检索攻坚与验证）**：FR-3b 移植已提前完成（等回归开启）；FR-7、试用招募未开工。
- 环境注记：本开发环境缺 chromadb/langchain-chroma（导入时联网下载模型受阻），27 个依赖真实向量库的存量测试在基线与本轮完全一致地失败；CI 环境需完整依赖方可运行全量套件。
