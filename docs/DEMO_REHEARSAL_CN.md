# MindDock 下午演示彩排稿

## 1. 演示目标

这次演示的目标，是让老师清楚看到三件事：

- MindDock 已经完成了一个真实可运行的后端 MVP
- 当前系统已经具备完整的 RAG 核心闭环
- 这个闭环不仅能跑通，而且适合现场稳定展示

观众看完后应该能理解：

“MindDock 已经完成了面向个人知识管理场景的可运行后端基础能力，包括本地 ingest、Chroma 持久化、检索、基于证据的问答、基于证据的总结、基于证据的多文档对比，以及知识库变化时的增量维护。”

## 2. 演示主线逻辑

整场演示建议围绕一条完整主线来讲：

1. 服务能够正常启动
2. 知识库可以被建立并持久化保存
3. 系统会先检索证据，而不是直接生成答案
4. 系统可以基于检索到的证据进行问答，并返回引用
5. 系统可以基于证据进行总结，而不是只做单点回答
6. 系统可以进行多文档对比，基于证据返回对比点和差异点
7. 当知识库文件变化时，系统还能进行增量维护

可以把这一整条链路概括成一句话：

“MindDock 当前已经完成了一个可运行的 RAG 后端闭环：本地知识入库、向量持久化、证据检索、带引用的问答与总结，以及基于 watcher 的增量维护。”

## 3. 演示前准备

### 环境

- 推荐直接使用 conda 环境 `minddock`
- 建议使用 Windows PowerShell
- 正式演示前先手动跑一遍完整链路，确认当前机器状态正常

创建并进入环境：

```powershell
conda env create -f environment.yml
conda activate minddock
```

如果环境已经建好，只需要：

```powershell
conda activate minddock
```

### 是否提前 ingest

- 建议提前执行一次：

```powershell
python -m app.demo ingest
```

- 这样可以保证 `data/chroma` 状态是最新的
- 正式演示时也可以再跑一次 `python -m app.demo ingest`，因为这条命令已经足够短，适合现场展示

### 是否提前启动 watcher

- watcher 建议单独开一个终端
- 最稳妥的方式是：前半程先不启动，等讲到增量维护时再运行
- 如果你想降低现场切换压力，也可以提前打开 watcher 终端并准备好命令

### 建议保留的样例文件

当前仓库中适合演示的文件：

- `knowledge_base/example.md`
- `knowledge_base/architecture.md`
- `knowledge_base/api_usage.md`
- `knowledge_base/rag_pipeline.md`
- `knowledge_base/knowledge_management.pdf`
- `knowledge_base/vector_databases.pdf`

### 推荐默认查询

当前最稳妥的默认查询词已经内置到 `app.demo` 命令里：

- query:
  - `MindDock stores document chunks and metadata in a local Chroma database`
- topic:
  - `MindDock stores document chunks and metadata in a local Chroma database`
- `top_k = 3`

也就是说，下面这些命令默认就能直接用：

```powershell
python -m app.demo search
python -m app.demo chat
python -m app.demo summarize
```

### 现场应避免的风险路径

下面这些不要在 live demo 里主动演示：

- 不要在 API 运行过程中调用 `/ingest` 且传 `rebuild=true`
  - 当前 Windows 下可能触发 Chroma 文件锁
- 不要现场演示 `source + section` 双过滤器搜索
  - 当前多过滤器路径不够稳定
- 不要把 rerank / compress 讲成已完成功能
  - 当前只是占位 hook
- 不要把 URL ingestion 讲成已完成
  - 当前未实现
- 不要把远程 OpenAI-compatible 路径作为主演示依赖
  - 如需稳定，优先依赖当前本地已验证链路

## 4. 推荐演示顺序（逐步操作版）

### Step 1. 启动服务

目的：

- 证明服务是真实可启动的
- 为后面的所有 API 演示建立前提

操作：

```powershell
conda activate minddock
python -m app.demo serve
```

讲解要点：

- “我先启动当前后端服务，后面的检索、问答和总结都运行在这个服务之上。”
- “这一步主要证明项目不是静态原型，而是可运行的后端系统。”
- “为了下午演示更流畅，我把常用流程收敛成了短命令层。”

预期现象：

- 终端显示服务启动完成
- 服务监听在 `http://127.0.0.1:8000`

风险提醒：

- 这个终端只留给服务，不要再输入其他命令
- 如端口冲突，可改用：
  - `python -m app.demo serve --port 8001`

### Step 2. 检查 `/` 和 `/health`

目的：

- 证明服务当前处于可用状态
- 给老师一个最简单、最直观的运行确认

操作：

```powershell
conda activate minddock
python -m app.demo root
python -m app.demo health
```

讲解要点：

- “这里先看基础接口，确认服务本身已经启动且健康。”
- “`/health` 是后续业务接口的最基础前提。”
- “通过这一步先建立‘系统已经跑起来’的印象。”

预期现象：

- `root` 返回服务名与版本
- `health` 返回 `status: ok`

风险提醒：

- 这一段不要展开太多技术细节，尽快进入主线

### Step 3. 执行 ingest

目的：

- 证明知识库是从本地文件真实建立出来的
- 说明 Chroma 中的数据不是写死在代码里

操作：

建议在第二个终端中执行：

```powershell
conda activate minddock
python -m app.demo ingest
```

讲解要点：

- “这一步会扫描 `knowledge_base` 目录，把文档切块、向量化，并写入 Chroma。”
- “当前仓库已经支持 Markdown、TXT 和 PDF 文档入库。”
- “我通常会在演示前先跑一遍，但现在现场再执行一次，说明这条链路是可复现的。”

预期现象：

- 控制台输出类似：
  - `Loaded ... documents`
  - `Created ... chunks`
  - `Stored to Chroma`

风险提醒：

- 只用 CLI 这条 ingest 命令，不要现场调用 API `/ingest` 做 rebuild

### Step 4. 演示 `/search`

目的：

- 证明系统会先做检索，再进入生成阶段
- 展示命中结果和 citation 基础结构

操作：

```powershell
conda activate minddock
python -m app.demo search
```

如需自定义：

```powershell
python -m app.demo search --query "local Chroma database" --top-k 3
```

讲解要点：

- “这里先展示证据检索，而不是直接让模型回答。”
- “返回结果里既有文本片段，也有 `source`、`chunk_id` 等信息。”
- “每条结果还带 citation，这为后面的问答和总结提供证据基础。”

预期现象：

- 返回格式化 JSON
- 第一条通常来自 `example.md`
- 可以看到：
  - `source`
  - `distance`
  - `citation.section`
  - `citation.ref`

风险提醒：

- 不要现场演示双过滤器版本
- 演示重点放在“先检索证据”上，不要过度展开相似度算法细节

### Step 5. 演示 `/chat`

目的：

- 证明系统可以基于检索结果生成 grounded answer
- 展示答案和 citation 是一起返回的

操作：

```powershell
conda activate minddock
python -m app.demo chat
```

如需自定义：

```powershell
python -m app.demo chat --query "MindDock stores document chunks and metadata in a local Chroma database" --top-k 3
```

讲解要点：

- “这里不是开放式聊天，而是先检索，再基于证据组织回答。”
- “你可以看到回答后面直接附带 citations，这意味着结果可追溯。”
- “无论是否接远程模型，这条 grounded 生成链路本身都已经打通。”

预期现象：

- 返回 `answer`
- 返回 `citations`
- 返回 `retrieved_count`
- citation 中可能包含 Markdown 和 PDF 来源

风险提醒：

- 不要把重点放在“在线大模型”上
- 更稳妥的说法是：当前已经完成 grounded 生成链路

### Step 6. 演示 `/summarize`

目的：

- 证明系统不仅能回答问题，也能基于证据做总结
- 说明 `/summarize` 和 `/chat` 共用同一条证据链

操作：

```powershell
conda activate minddock
python -m app.demo summarize
```

如需自定义：

```powershell
python -m app.demo summarize --topic "MindDock stores document chunks and metadata in a local Chroma database" --top-k 3
```

讲解要点：

- “`/summarize` 和 `/chat` 的区别在于输出目标不同，但底层都依赖检索证据。”
- “这说明系统已经形成了一套可复用的 RAG 后端能力，而不是单个接口。”
- “总结结果同样返回 citation，所以依然具备可解释性。”

预期现象：

- 返回 `summary`
- 返回 `citations`
- 返回 `retrieved_count`
- citation 里可能带 PDF 页码 `page`

风险提醒：

- 不要用过于宽泛的 topic
- 当前默认 topic 是最稳的现场选择

### Step 7. 演示 `/compare`

目的：

- 证明系统支持多文档对比，并返回对比点、差异点和冲突点
- 说明 compare 通过统一执行协议执行，与 search/chat/summarize 共用同一套检索链

操作：

```powershell
conda activate minddock
python -m app.demo compare
```
> **注**：`compare`（不带 `--via-api`）直接调用本地服务，绕过 HTTP 层。如需通过 API 调用，使用 `--via-api` 标志：`python -m app.demo compare --via-api`。

如需指定特定文档对比：

```powershell
python -m app.demo compare --filters doc_a.md,doc_b.md
```

讲解要点：

- "compare 是统一执行协议中的一等公民，与 search、chat、summarize 共用检索链。"
- "系统会返回 common_points（共同点）、differences（差异点）和 conflicts（冲突点）。"
- "每个对比点都附带来源证据和引用，答案可追溯。"
- "本地模式通过 facade 的 compare 兼容入口进入统一执行链，绕过 HTTP 层；使用 --via-api 时通过 /frontend/execute 调用。"

预期现象：

- 返回 `common_points`、`differences`、`conflicts`
- 返回 `support_status`（supported / insufficient_evidence 等）
- 返回 `citations`（每个对比点的证据引用）

风险提醒：

- 需要至少两个文档在知识库中才有实际对比意义
- 如果只有一个文档，系统会返回 insufficient_evidence

### Step 8. 演示 watcher 的 create / modify / delete

目的：

- 证明系统支持知识库增量维护
- 展示它不需要每次都全量 rebuild

操作：

先在新终端启动 watcher：

```powershell
conda activate minddock
python -m app.demo watch
```

然后在另一个终端执行：

创建文件：

```powershell
Set-Content -LiteralPath knowledge_base\demo_watch.md -Value @"
# Demo Watch
This file is created during the live demo.
The unique token is DEMO_WATCH_TOKEN_001.
"@ -Encoding UTF8
```

修改文件：

```powershell
Set-Content -LiteralPath knowledge_base\demo_watch.md -Value @"
# Demo Watch
This file is modified during the live demo.
The unique token is DEMO_WATCH_TOKEN_002.
"@ -Encoding UTF8
```

删除文件：

```powershell
Remove-Item -LiteralPath knowledge_base\demo_watch.md
```

如果想配合再检索一次：

```powershell
python -m app.demo search --query "DEMO_WATCH_TOKEN_001"
python -m app.demo search --query "DEMO_WATCH_TOKEN_002"
```

讲解要点：

- “前面的 ingest 展示的是全量建库，这一步展示的是知识库的持续维护能力。”
- “watcher 监听本地文件变化，只重建受影响的文档。”
- “create / modify / delete 三种场景都属于真实知识管理系统会遇到的操作。”

预期现象：

- watcher 终端输出 create / modify / delete 日志
- 创建后能检索到新 token
- 修改后旧内容被替换、新内容可检索
- 删除后文件相关内容不再命中

风险提醒：

- watcher 更适合手工演示，不适合追求毫秒级稳定
- 修改时不要连续快速保存很多次，避免 debounce 影响现场观感

## 5. 推荐使用的具体命令

### 创建并激活 conda 环境

```powershell
conda env create -f environment.yml
conda activate minddock
```

### 后续进入环境

```powershell
conda activate minddock
```

### 全量 ingest

```powershell
python -m app.demo ingest
```

### 启动 API

```powershell
python -m app.demo serve
```

### 查看根路由和健康检查

```powershell
python -m app.demo root
python -m app.demo health
```

### 检索、问答、总结、对比

```powershell
python -m app.demo search
python -m app.demo chat
python -m app.demo summarize
python -m app.demo compare
```

### watcher

```powershell
python -m app.demo watch
```

### 可选短别名

```powershell
python -m app.demo s
python -m app.demo c
python -m app.demo sum
python -m app.demo cmp
```

## 6. 推荐演示请求样例

### `/search`

最省事版本：

```powershell
python -m app.demo search
```

自定义版本：

```powershell
python -m app.demo search --query "local Chroma database" --top-k 3
```

### `/chat`

最省事版本：

```powershell
python -m app.demo chat
```

自定义版本：

```powershell
python -m app.demo chat --query "MindDock stores document chunks and metadata in a local Chroma database"
```

### `/summarize`

最省事版本：

```powershell
python -m app.demo summarize
```

自定义版本：

```powershell
python -m app.demo summarize --topic "MindDock stores document chunks and metadata in a local Chroma database"
```

说明：

- 这些默认参数已经按当前本地仓库的稳定 happy path 选好
- 现场如果不想冒风险，直接用默认命令即可

## 7. 推荐现场讲稿（简版）

### 开场 20-30 秒

“我这次展示的是 MindDock 当前已经完成的后端 MVP。它面向个人知识管理场景，核心思路是把本地知识库入库到 Chroma，然后通过检索增强生成的方式，实现基于证据的搜索、问答和总结。同时，系统还支持知识库变化后的增量维护，因此它已经不是停留在设计层面的原型，而是一个可运行、可验证、可继续迭代的后端系统。”

### 过渡语

- 从启动到健康检查：
  - “我先确认服务已经正常运行，后面的能力都建立在这个基础之上。”
- 从健康检查到 ingest：
  - “接下来我展示知识库是如何从本地文件建立起来的。”
- 从 ingest 到 search：
  - “系统第一步不是直接生成，而是先做证据检索。”
- 从 search 到 chat：
  - “在检索基础上，再做基于证据的问答。”
- 从 chat 到 summarize：
  - “除了回答问题，当前系统也可以对同一批证据做总结。”
- 从 summarize 到 compare：
  - “除了单个文档的总结，系统还支持多文档对比。”
- 从 compare 到 watcher：
  - “最后展示知识库变化后的增量维护能力。”

### 结尾 20-30 秒

“综合来看，MindDock 当前已经完成了一个可运行的 RAG 后端闭环：本地知识入库、Chroma 持久化、检索、带引用的问答与总结、带引用的多文档对比，以及 watcher 驱动的增量维护。下一步我会继续修复边界问题、提升检索质量，并补齐 URL 接入和工程化能力，使它进一步接近完整的毕业设计目标。”

## 8. 老师可能追问的问题

### 目前做到哪一步了？

建议回答：

“目前已经完成后端 MVP，核心 RAG 闭环已经可运行，包括本地 ingest、Chroma 持久化、search、chat、summarize、compare，以及 watcher 增量维护。”

### 当前最大的亮点是什么？

建议回答：

“最大的亮点是系统已经不是单点接口，而是形成了完整闭环，而且 compare、chat、summarize 都能返回 citation，PDF 也已经支持页码级引用。”

### 还没完成什么？

建议回答：

“当前还没完成 URL ingestion，rerank 和 compress 还是占位实现；多过滤器检索和 API 模式下 rebuild 的稳定性也还需要继续修复；CI 也尚未接入。”

### 下一步做什么？

建议回答：

“下一步会优先修复真实运行中的不稳定路径，提升检索质量，然后补充 URL ingestion 和工程化能力，比如 CI 和更完善的回归验证。”

## 9. 演示避坑清单

- 不要在 API 已运行时调用 `/ingest` 且传 `rebuild=true`
- 不要现场演示 `source + section` 双过滤器检索
- 不要把 rerank / compress 说成已经做完
- 不要把 URL ingestion 说成已经做完
- 不要把远程 OpenAI-compatible 接口作为主演示依赖
- 不要在 watcher 演示时连续快速保存很多次同一个文件
- 不要临场更换陌生查询词，优先使用默认 demo 命令
- 演示前最好先手动跑过一次 `python -m app.demo ingest`

## 附注

这份文档优先面向“下午直接彩排”的实际需求。如果后续命令层或环境方案继续变化，建议优先同步更新本文件、`README.md` 和 `docs/STATUS.md`。
