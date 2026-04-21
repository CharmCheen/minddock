# MindDock 演示流程（5 分钟版本）

> 本文档帮助你在答辩/展示时快速演示 MindDock 的核心功能。

---

## 演示准备

### 确认系统已启动

```bash
# 后端是否运行
curl http://127.0.0.1:8000/health
# 期望返回: {"status":"ok","service":"MindDock","version":"0.1.1"}

# 前端是否运行
# 访问 http://localhost:5173 应能看到界面
```

### 确认知识库已有内容

```bash
curl http://127.0.0.1:8000/sources
# 期望返回非空的 items 列表
```

如果返回为空，先运行入库：

```bash
python -m app.rag.ingest
```

---

## 演示一：Chat 问答（1 分钟）

**目标**: 展示基于本地知识库的带引用 RAG 问答。

**操作步骤**:

1. 在前端界面选择 **Chat** 模式
2. 输入问题，例如：

   > "这个知识库的主题是什么？"

   或：

   > "RAG 系统的核心组件有哪些？"

3. 观察返回结果中的 **References** 区域
4. 点击任意 reference，验证左侧文档列表是否同步高亮

**后端对应调用**:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "这个知识库的主题是什么？", "top_k": 3}'
```

**观察重点**:
- 答案中是否引用了具体来源（source + page/section）
- 答案是否与知识库内容相关（而非通用回答）
- "Insufficient evidence" 拒绝回答的场景

---

## 演示二：Summarize 摘要（1 分钟）

**目标**: 展示多文档摘要能力。

**操作步骤**:

1. 在前端选择 **Summarize** 模式
2. 输入主题，例如：

   > "RAG"

   或：

   > "知识管理"

3. 观察返回的摘要文本

**后端对应调用**:

```bash
# basic 模式（单次生成）
curl -X POST http://127.0.0.1:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"topic": "RAG", "top_k": 5, "mode": "basic"}'

# map_reduce 模式（跨文档汇总）
curl -X POST http://127.0.0.1:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"topic": "RAG", "top_k": 5, "mode": "map_reduce"}'
```

**观察重点**:
- 摘要是否综合了多个文档的内容
- 是否有 citations 引用（可点击跳转到文档）

---

## 演示三：Compare 对比分析（1 分钟）

**目标**: 展示结构化对比输出（common / differences / conflicts）。

**操作步骤**:

1. 在前端选择 **Compare** 模式
2. 输入对比问题，例如：

   > "比较 RAG 和 Fine-tuning 两种方法在知识管理上的优劣"

   或：

   > "对比向量数据库和知识图谱在 RAG 中的应用"

3. 观察三栏输出：Common Points / Differences / Conflicts

**后端对应调用**:

```bash
curl -X POST http://127.0.0.1:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"question": "比较 RAG 和 Fine-tuning 两种方法在知识管理上的优劣", "top_k": 6}'
```

**观察重点**:
- 系统是否正确识别出共同点、差异、冲突
- 冲突检测是否有依据（数字差异、否定词等）

---

## 演示四：Search 纯检索（1 分钟）

**目标**: 展示向量语义检索能力（不经过 LLM 生成）。

**操作步骤**:

1. 输入检索 query，观察返回的 chunk 列表
2. 注意每个结果有 `score`（语义相似度）和来源信息

**后端对应调用**:

```bash
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "RAG 检索增强生成", "top_k": 5}'
```

---

## 演示五：引用溯源（1 分钟）

**目标**: 展示 citation 的可追溯性。

**操作步骤**:

1. 完成一次 chat 后，找到 **References** 区域
2. 点击任意一条 reference
3. 验证左侧文档列表是否自动定位到对应文档
4. 确认 chunk 高亮是否正确

**后端数据结构验证**:

```bash
# 查看一条 chat 返回的 citations 结构
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "RAG 是什么", "top_k": 3}' | \
  python -m json.tool | grep -A 20 '"citations"'
```

每条 citation 应包含:
- `doc_id`: 文档唯一标识
- `chunk_id`: chunk 唯一标识
- `source`: 来源文件/URL
- `ref`: 可读引用字符串（如 "文档名 > page 3"）
- `page`: 页码（PDF）
- `snippet`: 引用原文片段

---

## 快速命令汇总

```bash
# 1. 启动后端
uvicorn app.main:app --port 8000

# 2. 入库文档
python -m app.rag.ingest

# 3. 健康检查
curl http://127.0.0.1:8000/health

# 4. 列出文档
curl http://127.0.0.1:8000/sources

# 5. Chat 问答
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "RAG 是什么", "top_k": 3}'

# 6. Summarize 摘要
curl -X POST http://127.0.0.1:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"topic": "RAG", "top_k": 5, "mode": "basic"}'

# 7. Compare 对比
curl -X POST http://127.0.0.1:8000/compare \
  -H "Content-Type: application/json" \
  -d '{"question": "RAG vs Fine-tuning", "top_k": 6}'

# 8. Search 检索
curl -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "RAG", "top_k": 5}'
```

---

## 故障快速定位

| 现象 | 可能原因 | 解决方法 |
|------|---------|---------|
| chat 返回 "Insufficient evidence" | 知识库为空或 query 不匹配 | `python -m app.rag.ingest` 重新入库 |
| 后端启动报错 | 缺少依赖 | `uv sync` 或 `pip install -e .` |
| 前端无法连接 | 后端未启动或端口不对 | 确认 uvicorn 在 8000 端口 |
| citation 为空 | 无匹配检索结果 | 增大 top_k 或检查入库是否成功 |
| PDF 内容为空 | PDF 是扫描件无文字 | 这是预期行为，扫描 PDF 无法提取文字 |
