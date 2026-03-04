# Agentic RAG PKM Assistant (V0.1)

本仓库用于实现「基于 AI 智能平台的个人知识管理助手（Agentic RAG PKM Assistant）」。
当前阶段已完成工程初始化与目录规范化，后续按 SRS/HLD/Extension Guide 逐步实现。

## 当前目标（来自文档）
- 多源知识接入与规范化入库（解析/清洗/分块/向量化/索引）
- 证据驱动跨文档问答（答案必须带引用）
- 多文档主题总结（Map-Reduce + 引用）
- Profile 可配置（输出模板、检索参数、技能组合）
- 可扩展架构（Ports & Adapters + Contract Tests）

## 目录说明
- `core/`: 任务编排与流程控制
- `domain/`: 领域模型（RawDoc/Chunk/Citation/Profile）
- `ports/`: 扩展边界接口契约
- `adapters/`: 连接器/解析器/向量库/LLM/插件等可替换实现
- `configs/`: connectors/plugins/providers/profiles 配置
- `tests/contract/`: 扩展契约测试
- `docs/`: SRS/HLD/扩展开发指南

## 后续实施建议
1. 先固化 `ports` 与 `domain` 契约。
2. 实现 MVP：`local_folder` + `web_url` 接入，问答与总结两条技能链。
3. 建立 contract test，保证新增扩展不破坏核心流程。
