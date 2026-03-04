# Extension Guide 扩展开发指南（Engineering Standard）
**Project**: Agentic RAG Personal Knowledge Management Assistant  
**Doc Type**: Engineering Guide (Extension & Integration Standard)  
**Version**: v1.1  
**Date**: 2026-03-04  
**Owner**: 项目维护者（毕设作者）  
**Audience**: 扩展开发者（新增数据源/解析器/向量库/模型/工具插件）  

---

## 0. 目的与适用范围

### 0.1 目的（Purpose）
本指南定义系统“可扩展边界（Extensible Boundaries）”的工程标准与接口契约（Contracts），目标是实现：
- **新增能力不改核心**：新增数据源、工具、模型、存储只需新增 Adapter/Plugin；
- **热插拔**：通过配置启停扩展模块；
- **可回归**：新增扩展必须通过契约测试（Contract Tests）；
- **可迁移**：模型/向量库/解析器可无感切换（配置驱动）。

### 0.2 适用范围（Scope）
本指南覆盖以下扩展面：
1) Data Connectors（数据连接器）  
2) Document Parsers（文档解析器）  
3) Vector Stores（向量库/检索引擎）  
4) LLM Providers（模型提供方，含多模型分工）  
5) Tool Plugins（OpenAPI 工具插件与动态注册）  

不在本指南范围：
- 模型微调训练与分布式训练集群；
- 企业级多租户与复杂权限审计（可作为后续扩展议题）。

---

## 1. 架构原则（Ports & Adapters）

### 1.1 依赖倒置
- **Core** 只依赖 **Ports（接口）**，禁止直接依赖任何外部系统 SDK/API（Notion、Qdrant、OpenAI 等）。
- **Adapters/Plugins** 实现 Ports，将外部系统能力“适配”为统一契约。

### 1.2 稳定与变化分离
- 稳定：领域模型（RawDoc/Chunk/Citation/Profile）、技能编排（Skills/Workflow）、RAG 主流程  
- 变化：数据源、解析器、向量库、模型、工具插件、触发器与通知渠道

### 1.3 可进可退（Feature Flags）
所有扩展模块必须通过配置提供 `enabled` 开关，保证：
- MVP 可最小化交付；
- 进阶模块可逐步启用；
- 出现故障可快速禁用并回退。

---

## 2. 推荐工程目录（Reference Layout）

```text
pkm-agent/
  core/                      # 稳定：流程编排、技能执行、策略
  domain/                    # 稳定：领域对象
  ports/                     # 稳定：接口契约（扩展边界）
  adapters/                  # 变化：可替换实现（新增扩展主要发生在此）
  configs/                   # 配置：profiles/connectors/plugins/providers
  tests/contract/            # 契约测试：扩展上线门槛
  docker/                    # 可选：容器化编排
  docs/                      # 文档：SRS/HLD/Extension Guide
```

---

## 3. 领域数据契约（Domain Contracts）

> **关键要求**：所有扩展必须输出/使用统一领域对象；引用能力是系统工程可信度核心。

### 3.1 RawDoc（入库前统一对象）
字段要求（MUST/SHOULD）：
- MUST: `source`, `source_uri`, `title`, `content`
- SHOULD: `created_at`, `updated_at`, `tags`, `meta`

```python
from dataclasses import dataclass
from typing import Dict, Optional, List

@dataclass
class RawDoc:
    source: str
    source_uri: str
    title: str
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tags: Optional[List[str]] = None
    meta: Optional[Dict] = None
```

### 3.2 Chunk（检索与引用的最小证据单元）
字段要求：
- MUST: `doc_id`, `chunk_id`, `text`
- MUST: `location`（页码/段落锚点/时间戳等至少一种可定位信息）
- SHOULD: `section_path`（标题层级），`meta`

> location 的设计建议：  
> - PDF: `p12` 或 `p12-13`  
> - HTML: `url#h2-xxx` 或 DOM anchor  
> - MD: `file.md#section`  
> - 视频字幕: `t=00:02:31`  

### 3.3 Citation（引用）
引用条目必须能满足答辩/论文“可追溯”要求：
- `ref`: 文档标题/来源
- `quote`: 证据片段（可截断）
- `location`: 可定位信息（页码/锚点/时间戳）
- `chunk_id`: 与检索命中绑定（避免“伪引用”）

---

## 4. Port 规范（Extension Ports）

以下 Ports 是系统扩展边界，任何新增实现必须满足接口语义。

### 4.1 DataConnector（数据连接器）
**职责**：从任意数据源拉取/读取数据并输出 RawDoc 流。

```python
from abc import ABC, abstractmethod
from typing import Iterable
from domain.models import RawDoc

class DataConnector(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def fetch(self) -> Iterable[RawDoc]:
        "Return iterable RawDoc objects."
```

**语义约束**：
- `fetch()` 必须可重复运行（幂等或具备增量策略）。
- 连接器不得在 `fetch()` 内直接写入向量库（保持职责单一）。

### 4.2 DocumentParser（文档解析器）
**职责**：将“载体（文件/URL/HTML/PDF 等）”解析为规范文本与结构信息。

```python
from abc import ABC, abstractmethod
from typing import Dict

class DocumentParser(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def parse(self, raw: Dict) -> Dict:
        # RECOMMENDED return keys:
        # - text: str
        # - sections: list (optional)
        # - pages/location_map: (optional)
        # - meta: dict (optional)
        raise NotImplementedError
```

### 4.3 VectorStore（向量库/检索引擎）
**职责**：Upsert 向量条目与检索命中。

```python
from abc import ABC, abstractmethod
from typing import List, Dict

class VectorStore(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def upsert(self, items: List[Dict]) -> None:
        # item fields: doc_id, chunk_id, text, embedding, meta, location, section_path
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, top_k: int, filters: Dict) -> List[Dict]:
        # return hit fields: doc_id, chunk_id, text, score, location, meta
        raise NotImplementedError
```

### 4.4 LLMProvider（模型提供方）
**职责**：生成（可扩展为结构化输出/工具调用模式）。

```python
from abc import ABC, abstractmethod
from typing import List, Dict

class LLMProvider(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def generate(self, messages: List[Dict], **kwargs) -> str: ...
```

### 4.5 ToolPlugin / ToolRunner（OpenAPI 工具插件）
**职责**：动态注册、解析可调用操作、执行调用。

- 插件应提供 OpenAPI spec（JSON），包含 `paths` 与 `operationId`
- ToolRunner 负责鉴权、请求构造、返回值规范化（JSON）

---

## 5. 配置驱动（Config-driven Extension）

### 5.1 connectors.yaml（数据连接器启停）
```yaml
connectors:
  - type: local_folder
    enabled: true
    args:
      folder: "./data/notes"
  - type: web_url
    enabled: true
    args:
      urls:
        - "https://example.com/article"
```

### 5.2 plugins.yaml（OpenAPI 插件注册表）
```yaml
plugins:
  - name: web_extractor
    enabled: true
    openapi_url: "http://localhost:8001/openapi.json"
    auth: {}
```

### 5.3 providers.yaml（基础设施可替换）
```yaml
providers:
  parser:
    type: pdf_plumber
  vector_store:
    type: coze_kb      # 可切换: chroma / qdrant / milvus
  llm:
    router:
      type: openai
      model: gpt-4o-mini
    main:
      type: openai
      model: gpt-4o
    validator:
      enabled: false
      type: openai
      model: gpt-4o-mini
```

### 5.4 profiles.yaml（通用型可微调场景）
```yaml
profiles:
  - name: default
    enabled_skills: ["ask", "summarize"]
    retrieval: { top_k: 8, rerank: false }
    output:
      language: "zh"
      template: |
        ## 答案
        {{answer}}
        ## 引用
        {{citations}}
  - name: project
    enabled_skills: ["ask", "summarize", "brief"]
    retrieval: { top_k: 10, rerank: true }
    output:
      template: |
        ## 结论
        {{answer}}
        ## 证据（引用）
        {{citations}}
        ## 行动项
        - ...
```

---

## 6. 扩展流程（Engineering Workflow）

### 6.1 新增 DataConnector（Checklist）
1. 在 `adapters/connectors/` 新建文件 `xxx.py`  
2. 实现 `DataConnector`（name/fetch）  
3. 输出 `RawDoc`（满足 MUST 字段）  
4. 在 `configs/connectors.yaml` 添加条目并 `enabled: true/false`  
5. 通过契约测试（第 8 章）

### 6.2 新增 VectorStore（Checklist）
1. 在 `adapters/vector_store/` 新建实现类  
2. 实现 `upsert/search`  
3. 支持 `filters`（至少 tags/time/source_type）  
4. 在 `providers.yaml` 中可切换  
5. 通过 roundtrip 契约测试

### 6.3 新增 OpenAPI Plugin（Checklist）
1. 独立服务（建议 FastAPI）提供能力 endpoint  
2. 确保 OpenAPI spec 可访问（/openapi.json）  
3. 每个 endpoint 设置 `operationId`  
4. 将 `openapi_url` 注册到 `plugins.yaml`  
5. 运行“工具发现（discover）”自检（第 8 章）

---

## 7. 安全与兼容性要求（Security & Compatibility）

### 7.1 插件鉴权（Minimum Standard）
- 支持 bearer token / apiKey（最小实现）
- token 只从环境变量/密钥管理读取，不硬编码、不写日志

### 7.2 兼容性（SemVer）
- 破坏接口兼容：提升 MAJOR  
- 新增能力保持兼容：提升 MINOR  
- bugfix/文档：提升 PATCH

---

## 8. 契约测试（Contract Tests）与质量门槛

> 目标：扩展上线前必须可自动验证，不依赖人工“跑一下看看”。

### 8.1 Connector 契约测试（示意）
```python
def assert_rawdoc(doc):
    assert doc.title and isinstance(doc.title, str)
    assert doc.source and isinstance(doc.source, str)
    assert doc.source_uri and isinstance(doc.source_uri, str)
    assert doc.content and isinstance(doc.content, str)

def test_connector_contract(connector):
    docs = list(connector.fetch())
    assert len(docs) >= 1
    for d in docs[:3]:
        assert_rawdoc(d)
```

### 8.2 VectorStore Roundtrip（示意）
```python
def test_vectorstore_roundtrip(vector_store):
    items = [{
        "doc_id": "D1",
        "chunk_id": "C1",
        "text": "hello world",
        "embedding": [0.1]*8,
        "location": "p1",
        "meta": {"tags":["test"]}
    }]
    vector_store.upsert(items)
    hits = vector_store.search("hello", top_k=3, filters={"tags":["test"]})
    assert isinstance(hits, list)
```

### 8.3 Plugin Discover 自检（示意）
- 拉取 openapi.json
- 校验 paths 存在 operationId
- 记录可调用 tools 列表（用于调试与论文材料）

---

## 9. 典型扩展示例（Template Snippets）

### 9.1 示例：新增 Connector（视频字幕）
```python
from ports.connectors import DataConnector
from domain.models import RawDoc

class SubtitleConnector(DataConnector):
    def __init__(self, video_id: str):
        self.video_id = video_id

    def name(self) -> str:
        return "subtitle"

    def fetch(self):
        text = "Subtitle text..."
        yield RawDoc(
            source="video",
            source_uri=f"video://{self.video_id}",
            title=f"subtitle_{self.video_id}",
            content=text,
            tags=["subtitle"],
            meta={"video_id": self.video_id}
        )
```

### 9.2 示例：最小 OpenAPI 插件（FastAPI）
```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="PKM Tool Plugin")

class Req(BaseModel):
    url: str

class Resp(BaseModel):
    title: str = ""
    text: str = ""

@app.post("/extract", response_model=Resp, operation_id="extract_web_page")
def extract(req: Req):
    return Resp(title=req.url, text="...")
```

---

## 10. Quick Start（最短可用路径）
- 先把 **Ports（接口）** 定死（不改）  
- 以 `local_folder` + `web_url` 两个 connector 跑通入库  
- 用平台知识库作为 VectorStore（MVP）  
- 做 2 个 skills（ask + summarize）+ 固定引用格式  
- 后续再逐步启用：mindmap / plugins / multi-model / rerank  

---

**End of Document**
