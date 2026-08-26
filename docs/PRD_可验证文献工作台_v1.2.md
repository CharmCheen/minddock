# PRD 产品需求文档（PRD）
**项目名称**：MindDock 可验证文献工作台（Verifiable Literature Workbench）
**版本**：v1.2
**日期**：2026-08-25
**文档状态**：多方评审（PM × CTO × 前端专家 × 后端专家 双轮辩论收敛）；替代 v1.1
**前置文档**：`docs/SRS_个人知识管理助手_v1.0.md`、`docs/ROADMAP.md`、`docs/thesis-alignment.md`

## 修订记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-08-25 | 双 agent（PM × CTO）评审定稿：定位、P0 范围、修正后排期、Non-goals、决策纪要 |
| v1.1 | 2026-08-25 | 同步首轮实现状态（FR-1/2/3/4/6/9 完成，FR-3b 移植完成待回归开启）；FR-9 提前交付；附录 B 开放问题部分关闭；新增第 13 节实现状态与偏差记录 |
| v1.1.1 | 2026-08-25 | 二轮开发同步：FR-5 扩容至 29 例（部分）、FR-7 综述工作台 MVP、FR-8 MCP POC 完成；附录 C 状态矩阵更新；评测护栏测试随 FR-5 政策调整 |
| v1.2 | 2026-08-25 | 四方双轮辩论定稿（附录 D）：四大议题裁决——检索攻坚主线确认、综述独立端点修复（一期）+管线并入（二期）、徽章分档分批显示、MCP 冻结+冒烟闭环；新增 P0/P1 缺陷清单（综述假信号/runtime 未注入、SSE info 不可见、双徽章冲突）；下一里程碑 Top-3（修复:新功能 = 2:1） |

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
| FR-5 评测集扩容 50 例 | 🟡 部分完成（13→29 例，离线验证 chunk 映射） | `2203823` | 数据集护栏测试同步更新；剩余 ~21 例需对内置学术 PDF 做运行时解析与人工标注；**G2 指标承诺仍挂起** |
| FR-7 综述工作台 | ✅ MVP 完成（后端） | `f25d285` | `POST /frontend/review-workbench`：review.v1 结构化负载 + 可点击引用 + 无 runtime 时确定性抽取降级；前端专用渲染面板未做（当前走通用 JSON 渲染）。**⚠️ 辩论发现 P0 缺陷，见第 14 节 D-1** |
| FR-8 MCP POC | ✅ POC 完成 | `dbbf881` | `tools/minddock_mcp_server.py` 只读 stdio server（minddock_search）；未做真实客户端联调；**⚠️ 传输帧格式存疑（newline-delimited vs Content-Length），见第 14 节 D-6** |

### 里程碑实际进展（对照第 8 节）

- **M1（信任内核）**：FR-5 之外全部达成（徽章、自检 MVP、trace 落盘均可用）；评测集扩容顺延为 M2 首项。
- **M2（工作台成形）**：FR-3/FR-4 已提前完成；剩余为徽章定标展示（依赖 50 例集）与评测扩容。
- **M3（检索攻坚与验证）**：FR-3b 移植已提前完成（等回归开启）；FR-7、试用招募未开工。
- 环境注记：本开发环境缺 chromadb/langchain-chroma（导入时联网下载模型受阻），27 个依赖真实向量库的存量测试在基线与本轮完全一致地失败；CI 环境需完整依赖方可运行全量套件。

---

## 14. 附录 D：四方双轮辩论纪要（v1.2，2026-08-25）

参与方：产品经理（PM）、技术总监（CTO）、前端专家、后端专家。流程：第一轮各自立论（含对现有实现的代码级批判）→ 第二轮交叉投喂互辩（反驳 + 让步 + 最终裁决）→ 本附录定稿。

### D-0 辩论议题与最终裁决总表

| 议题 | PM | CTO | 前端 | 后端 | **最终裁决（收敛后）** |
|---|---|---|---|---|---|
| ① 部署 vs 检索攻坚 | 检索 | 检索 | 检索 | 检索 | **检索攻坚为主线**；部署维持 P2（高接触装机覆盖 10 人试用即可，不做 pip 包） |
| ② 综述工作台并入管线 vs 独立端点 | 并入（两期） | 并入（先摘假信号） | 并入 | 并入（先注 runtime） | **一期独立端点修复（2 周可交付）→ 二期并入统一管线**（TaskType/计划分支/事件壳一次到位） |
| ③ 徽章立即全量显示 | 支持 | 反对 | 条件支持 | 条件支持 | **分档分批**：前置门禁通过后红黄先行，绿章待一致率 ≥85% |
| ④ MCP 加固转正 vs 冻结观察 | 冻结+联调 | 冻结+联调 | 冻结 | 偏冻结+1 天冒烟 | **冻结功能扩展；放行 ≤1 天真实客户端冒烟闭环，随后冻结生效** |

### D-1 辩论发现的 P0 缺陷（综述工作台，必修）

CTO 与后端独立发现并交叉验证（代码证据已核实）：

1. **假信号**：`review_workbench_service.py` 将 `quality_ok=True`、`low_confidence=False`、`support_status="supported"` 硬编码进手工 trace——综述页面必然出示绿徽章。
2. **runtime 未注入**：`app/api/routes.py` 调 `run_review_workbench(request)` 未传 runtime → LLM 合成永远落 `skipped_no_runtime` 降级分支且对用户无明示；服务内自检亦显式 `runtime=None`，LLM 层永久关闭。
3. **task_type 伪装**：路由层把徽章计算 task_type 硬编码为 `"summarize"`。
4. **定性**：三方一致定性为"自杀级缺陷"——对"敢给答案打分"的定位构成系统性破坏。修复与徽章显示门禁联动（D-3 前置①）。

### D-2 辩论发现的 P1 缺陷（前端，必修）

1. **SSE info 事件不可见**：`verification_completed` → info client event 已投影，但 `agent-message-list.tsx` `TurnWorkflowDetails` 对未知事件仅渲染原始字符串，message 永不展示——自检结果在会话时间线实际不可见。
2. **双徽章冲突**：`raw-artifact-viewer.tsx` `buildStatusBadges` 同屏渲染新 "Evidence: Strong" 徽章与旧 "Supported" 芯片——同一可信度两套词汇、配色互斥。
3. **自检面板丢 reasons**：`CitationSelfCheckPanel` 仅渲染 `[ref] status doc_id`，丢弃判定理由、不可点击跳 chunk。
4. **导出只做一半**：无 `.bib` 文件下载（仅剪贴板）。
5. **过滤器无 UI**：FR-3 的 author/year 后端已交付，前端设置/输入侧均无入口。
6. **空状态文案未提**徽章/自检/导出等新能力。

### D-3 徽章显示的放行门禁（议题③裁决细化）

**前置（缺一不可，互为门禁）**：
1. D-1 假信号摘除完成（runtime 注入 + 真实/缺席质量信号 + task_type 实名）；绿章缺席时援 compare 先例降级 unknown。
2. 双徽章合并为单一 Evidence 徽章（删旧 Supported 芯片；前后端同源 `compute_evidence_badge`）。
3. feature flag 默认关 + Beta 标注 + 悬停展示信号构成（tooltip 必须披露映射依据）。

**放行阶梯**：
- 红黄两档：门禁通过后**默认开**（红黄是风险提示，可先真后全）。
- 绿章：待自检双层真实跑通 + 一致率 ≥85%（35 例首批定标）再放行。
- 黄档不得砍（PM 红线）：向用户展示"我们不确定"是差异化诚实卖点。

### D-4 议题②综述工作台的最终技术方案

- **一期（2 周）**：独立端点修复——摘除假信号（真实计算或缺席降级 unknown）、RuntimeResolver 注入 runtime（签名不变）、task_type 实名 `review_workbench`、自检透传 runtime 且 LLM 层 skipped 状态进 trace 驱动徽章降级；前端把 review.v1 作为一等卡片渲染（表格 + CitationList + 徽章，禁止落 JSON dump）。
- **二期（后续里程碑）**：并入统一执行管线——TaskType 枚举 + 计划分支 + SSE 事件壳一次到位，获得 SSE/取消/trace 归档/run replay；一期接口（runtime 注入点、metadata schema）冻结，二期不得回改。

### D-5 议题①下一里程碑 Top-3（修复：新功能 = 2:1）

1. 【修复】综述假信号根治 + runtime 注入 + CI 依赖治理（安装 chromadb/langchain-chroma），恢复 FR-3b 双回归与 G1/G2 评测资格。
2. 【修复/度量】35 例首批评测定标跑通（来源一致率接入显示门槛）+ 双徽章合并 + 红黄先行 flag。
3. 【新功能/修补】前端修复包：SSE info 可见化（S）、.bib 下载（S）、双徽章合并（S）、自检面板 reasons+点击（M）、过滤器 UI 仅作者+年份两输入框（M）。

### D-6 议题④MCP 冒烟验收标准

- 用真实 MCP 客户端（Claude Desktop 或 Cursor）完成一次 initialize + tools/list + tools/call 冒烟并录屏。
- **先验证传输帧格式**：当前实现为 newline-delimited JSON-RPC，若客户端要求 Content-Length 帧则需先修传输层再冒烟。
- 冒烟通过 → 冻结生效（不外宣、不加写工具）；转正触发器：试用用户 ≥3 人主动提出，或 G2/G3 达标后进入 Source Skill 边界设计。

### D-7 各方红线（已纳入门禁）

| 方 | 红线 |
|---|---|
| PM | 徽章可分期降档，但不能"永远只埋点不上显"；黄档不得砍；tooltip 必须披露结论依据 |
| CTO | 假信号绝不带病上线（D-1 未修，徽章 flag 禁开）；FR-3b 回归未开启，检索侧改动禁合并；双徽章并存视图禁入对外演示 |
| 前端×后端（联名） | runtime 注入接口签名冻结；自检 metadata schema 只增不改；SSE 事件壳冻结后再迁 |

### D-8 结论

四方在"先把信任资产修好，再让信任可见"上完全一致。下一里程碑是**修复冲刺**而非功能冲刺：假信号根治、评测地基恢复、显示门禁打通。G3 试用（10 人）在门禁通过后启动，高接触装机。
