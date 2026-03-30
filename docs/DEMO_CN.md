# MindDock 演示说明

## 1. 项目简介
MindDock 是一个面向个人知识管理场景的后端系统，当前以 RAG 为核心，支持本地知识入库、Chroma 持久化检索、带引用的问答与总结，以及知识库变更后的增量维护。项目目前处于毕业设计的持续迭代阶段，目标是先把可运行、可验证、可演示的后端闭环做扎实，再逐步补齐更完整的能力。

## 2. 当前完成情况

当前已经完成并可演示的部分包括：

- 后端服务可正常启动
- `GET /` 和 `GET /health` 可正常访问
- 本地知识库文件可执行 ingest
- 已支持 `.md`、`.txt`、`.pdf` 文件入库
- Chroma 向量数据可持久化到本地目录
- `POST /search` 可在基础场景下返回检索结果
- `POST /chat` 可返回带 citation 的回答
- `POST /summarize` 可返回带 citation 的总结
- citation 结构已统一，便于说明结果来源
- watcher 增量更新已支持 create / modify / delete
- PDF 文档已可入库，并可返回带页码的引用

## 3. 推荐演示链路

推荐按照下面顺序进行现场展示：

1. 启动服务
2. 检查 `GET /health`
3. 执行一次 ingest / rebuild
4. 演示 `POST /search`
5. 演示 `POST /chat`
6. 演示 `POST /summarize`
7. 启动 watcher，演示本地文件 create / modify / delete 的增量更新

推荐命令：

```powershell
conda env create -f environment.yml
conda activate minddock
python -m app.demo ingest
python -m app.demo serve
```

另开终端后可继续：

```powershell
conda activate minddock
python -m app.demo health
python -m app.demo search
python -m app.demo chat
python -m app.demo summarize
python -m app.demo watch
```

## 4. 演示重点说明

汇报时建议重点强调以下几点：

- 这是一个真实可运行的后端系统，而不是只停留在接口设计或原型图
- 检索、问答、总结已经形成一个可运行的核心闭环
- 回答和总结都能返回 citation，突出“可追溯、可解释”
- PDF 文档已经纳入知识库，并支持页码级引用
- 知识库支持 watcher 增量维护，不需要每次都全量重建

## 5. 当前未完成内容

当前仍需诚实说明尚未完成或仍在完善的部分：

- URL 接入尚未实现
- rerank / compress 仍然是占位实现
- 多过滤器检索在当前 Chroma 行为下稳定性仍需修复
- `/ingest` 的 `rebuild=true` 在长时间运行的 API 模式下，Windows 上可能受到文件锁影响
- CI 还未接入
- 更高阶的 workflow / agent 能力尚未完成

## 6. 下一步计划

短期内的优先工作包括：

1. 修复多过滤器检索与 rebuild 模式的真实运行问题
2. 提升检索质量与本地演示稳定性
3. 补充 URL ingestion
4. 为 rerank / compress 提供更实际的第一版能力
5. 增加 CI，并持续同步 README、状态文档与演示文档

## 7. 可直接用于汇报的简短话术

目前 MindDock 已经完成了一个可运行的后端 MVP。系统支持本地知识文件入库，使用 Chroma 做持久化检索，并能通过 `/search`、`/chat`、`/summarize` 提供带引用的结果。同时，项目已经具备基于 watcher 的增量更新能力，PDF 文档也已纳入支持范围。现阶段我重点在继续修复真实运行中的边界问题，并逐步向更完整的毕业设计目标推进。
