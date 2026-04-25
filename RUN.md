# MindDock 运行说明

本文档给出最稳的本地运行路径，用于毕业设计演示和答辩前自检。

## 1. 环境要求

- Python 3.11
- Conda 环境名：`minddock`
- Node.js 18+，npm
- 可选：LLM API key。未配置时系统会使用 mock fallback，流程可跑通，但生成质量不代表真实模型效果。
- Chroma 数据目录：`data/chroma/`
- 演示文档目录：`knowledge_base/`

## 2. 创建后端环境

首次运行：

```powershell
conda env create -f environment.yml
conda activate minddock
```

如果环境已存在：

```powershell
conda activate minddock
```

安装项目依赖：

```powershell
pip install -e ".[dev]"
```

## 3. LLM 配置

如果需要真实模型生成，请准备 `.env` 或通过前端 runtime settings 配置模型。

可参考：

```powershell
copy .env.minimax.local .env
```

然后填入自己的 API key。不要把真实 key 提交到 Git。

没有 API key 时，系统会走 mock fallback，适合验证 API、检索、citation、source 展示链路。

## 4. 构建或复用索引

仓库中已有 `knowledge_base/` 示例文档，也可能已有 `data/chroma/` 索引。

如果需要重新入库：

```powershell
conda run --no-capture-output -n minddock python -m app.demo ingest
```

如果只想追加 URL：

```powershell
conda run --no-capture-output -n minddock python -m app.demo ingest --no-rebuild --url https://example.com
```

### Sync-once / Watch

推荐用 `watch --once` 做增量同步演示：

预览变更（不实际写入）：

```powershell
conda run --no-capture-output -n minddock python -m app.demo watch --once --dry-run
```

同步一次并退出：

```powershell
conda run --no-capture-output -n minddock python -m app.demo watch --once
```

持续监听：

```powershell
conda run --no-capture-output -n minddock python -m app.demo watch --path knowledge_base --debounce 2.0
```

Watcher 扫描 `.pdf`、`.md`、`.txt`、`.csv` 文件和 `.png`/`.jpg`/`.jpeg`/`.webp` 图片。新增文件会入库，修改文件按内容哈希替换，未变文件跳过，删除文件会同步移除 Chroma chunks 和 HashStore 记录。Windows 下建议等大文件复制完成后再同步，或先用 `--once --dry-run` 预览。

### URL ingest 说明

URL 只支持单页 static HTML 抽取：

- 抓取一个 HTTP/HTTPS URL
- 提取 title、可读正文、canonical URL 和 description metadata
- 优先 `article` / `main` 内容，回退到可读 body text
- 移除 script、style、nav、header、footer、aside 等噪声区域

URL 不支持：JavaScript 渲染、爬取、登录态、反爬、RSS、图片/视频/音频抽取、前端预览。

URL chunks 携带 `source_media=text`、`source_kind=web_page`、`loader_name=url.extract`。loader warnings 以短 metadata 形式存储，不进入 embedding 输入。

### Image OCR ingest 说明

Image 支持 `knowledge_base/` 下的 `.png`、`.jpg`、`.jpeg`、`.webp`。

图像通过 OCR 转为文本后，复用现有文本 RAG 路径：`SourceLoadResult -> chunking -> Chroma -> retrieval -> citation`。

默认使用 mock OCR fallback，仅验证 pipeline 通路，不代表真实图像理解。配置 `IMAGE_OCR_PROVIDER=rapidocr` 且已安装 RapidOCR 时，可使用真实 OCR。RapidOCR 不是硬依赖，缺失时安全回退 mock。

Image chunks 携带 `source_media=image`、`source_kind=image_file`、`loader_name=image.ocr`、`ocr_provider`、`retrieval_basis=ocr_text`、`image_filename`。

不支持：image caption、PDF figure extraction、video/audio、multimodal embedding、OCR table reconstruction、layout blocks、frontend image preview。

### CSV source skill 说明

CSV 支持 `knowledge_base/` 下的 `.csv` 文件。

使用 Python 标准库 `csv` 解析，无需 pandas。支持 UTF-8 和 UTF-8 BOM，自动识别 header，无 header 时生成 `Column 1`、`Column 2` 等列名。行数超过 500 时截断并标记 `csv_truncated` warning。

CSV 行被转换为可读文本后进入标准 RAG 路径。metadata 包含 `source_media=text`、`source_kind=csv_file`、`loader_name=csv.extract`、`retrieval_basis=csv_rows_as_text`、`csv_filename`、`csv_columns`、`csv_row_count`、`csv_rows_indexed`。

不支持：Excel、SQL、表格推理引擎、chart generation。

## 5. 启动后端

推荐演示命令：

```powershell
conda activate minddock
python -m app.demo serve
```

默认地址：

```text
http://127.0.0.1:8000
```

也可以直接使用 uvicorn：

```powershell
uvicorn app.main:app --reload --port 8000
```

健康检查：

```powershell
conda run --no-capture-output -n minddock python -m app.demo health --via-api
```

或浏览器打开：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

## 6. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

Vite 默认地址：

```text
http://localhost:5173
```

前端构建检查：

```powershell
cd frontend
npm run build
```

## 7. Demo CLI 常用命令

列出已索引 sources：

```powershell
conda run --no-capture-output -n minddock python -m app.demo sources
```

查看某个 source 的 chunks：

```powershell
conda run --no-capture-output -n minddock python -m app.demo source-chunks --source rag_pipeline.md --limit 5
```

检索：

```powershell
conda run --no-capture-output -n minddock python -m app.demo search --query "Milvus system design" --top-k 4
```

问答：

```powershell
conda run --no-capture-output -n minddock python -m app.demo chat --query "What does the SYSTEM DESIGN section of the Milvus paper describe?" --top-k 4
```

查看 workflow trace：

```powershell
conda run --no-capture-output -n minddock python -m app.demo chat --query "What does the SYSTEM DESIGN section of the Milvus paper describe?" --top-k 4 --trace
```

`--trace` 打印结构化 pipeline metadata，例如 requested `top_k`、内部 candidate count、已触发的 deterministic rules 和最终 source 摘要。它不改变检索、回答生成或 citation 生成，也不暴露模型隐藏推理。

摘要：

```powershell
conda run --no-capture-output -n minddock python -m app.demo summarize --topic "Milvus system design" --top-k 4
```

对比：

```powershell
conda run --no-capture-output -n minddock python -m app.demo compare --question "Compare the Milvus paper with the local RAG pipeline docs." --top-k 4
```

CSV source skill 快速验证：

```powershell
# 假设 knowledge_base/ 下已有 data.csv
conda run --no-capture-output -n minddock python -m app.demo watch --once
conda run --no-capture-output -n minddock python -m app.demo source-detail --source data.csv
conda run --no-capture-output -n minddock python -m app.demo chat --query "data.csv 里第三行是什么?"
```

评测：

```powershell
conda run --no-capture-output -n minddock python -m app.demo evaluate --dataset eval/benchmark/sample_eval_set.jsonl
```

## 8. 测试命令

近期 RAG citation / retrieval 核心回归：

```powershell
conda run --no-capture-output -n minddock python -m pytest tests/unit/test_evidence_window.py tests/unit/test_retrieval_models.py tests/unit/test_pdf_citation.py tests/unit/test_citation.py tests/unit/test_schemas.py tests/unit/test_postprocess.py tests/unit/test_chat_service.py tests/unit/test_search_service.py tests/unit/test_csv_loader.py tests/unit/test_source_skill_catalog.py -q
```

项目 baseline：

```powershell
conda run --no-capture-output -n minddock python scripts/run_ci_baseline.py
```

前端类型和构建：

```powershell
cd frontend
npm run build
```

## 9. 常见问题

### 未配置 API key

系统会使用 mock fallback。可以演示检索、citation、source drawer 和 API 流程，但生成文本质量不代表真实模型。

### Embedding 模型或 CUDA 问题

如果 `sentence-transformers` 或 GPU 不可用，系统可能降级或变慢。演示前建议提前运行一次 ingest/chat，确认 `data/chroma/` 可用。

### `data/chroma/` 不存在或检索为空

运行：

```powershell
conda run --no-capture-output -n minddock python -m app.demo ingest
```

然后再调用 `sources` 或 `chat`。

### Embedding dimension mismatch

如果本地 Chroma 中混有不同 embedding 维度的历史数据，query 时会报错：`Embedding dimension X does not match collection dimensionality Y`。解决方法是重建索引：

```powershell
conda run --no-capture-output -n minddock python -m app.demo ingest --rebuild
```

### 前端端口

Vite 默认是 `5173`。如果端口被占用，终端会提示新的端口。

### Windows 中文路径和编码

建议使用 PowerShell，并确保终端使用 UTF-8。仓库路径包含中文时，优先使用 `conda run --no-capture-output -n minddock ...`，避免环境和编码差异。

### URL 只支持 static HTML

不支持 JavaScript 渲染、登录态、反爬。动态网页（如飞书、Notion 公开页）通常无法正确抽取。

### CSV 不支持 Excel

`.csv` 可用，`.xlsx` 不可用。CSV skill 只做行转文本，不做表格推理。

### Image OCR 不是 image caption

Image OCR 提取的是图中文字，不是对图像内容的描述性 caption。也不支持 PDF 内嵌 figure 提取。
