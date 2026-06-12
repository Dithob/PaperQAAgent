# QAAgent 中文使用手册

QAAgent 是一个用于论文搜索、PDF 阅读和论文问答的 Web 应用。当前版本是可运行的 MVP，适合个人或小组本地试用、二次开发和功能验证。

## 1. 已实现能力

- 搜索开放论文源：OpenAlex、Semantic Scholar、Crossref、arXiv。
- 显示每个论文源的搜索状态，单个源失败不会污染论文结果。
- 支持 PDF-only 过滤。
- 导入论文元数据和开放 PDF。
- 上传本地 PDF。
- 解析 PDF 的文本、页码和文本块坐标。
- 在浏览器中阅读 PDF。
- 对单篇论文提问，并返回带页码证据的回答。
- 点击问答证据后跳转到 PDF 对应页并高亮相关区域。
- 在设置面板中选择 LLM 服务商、模型、base URL、temperature 和 max tokens。
- API Key 保存在浏览器本地，不写入后端数据库。
- 支持 OpenAI、Azure OpenAI、Anthropic、Gemini、DeepSeek、Qwen、Moonshot/Kimi、Zhipu、OpenRouter、Ollama 和自定义 OpenAI-compatible 服务。

## 2. 目录说明

```text
QAAgent/
  apps/api/        FastAPI 后端
  apps/web/        Next.js 前端
  infra/init.sql   PostgreSQL + pgvector 数据库结构
  storage/pdfs/    本地 PDF 文件目录
  docker-compose.yml
  .env.example
```

## 3. 环境要求

本地开发已验证：

- Python 3.13
- Node.js 16.20.2
- npm 8.x

生产部署建议：

- Node.js 20+
- 升级 Next.js 和 PDF.js 到当前安全版本
- 使用 PostgreSQL + pgvector，而不是内存存储

## 4. 初始化配置

在项目根目录复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

常用配置项：

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
WEB_ORIGIN=http://localhost:3000
STORAGE_BACKEND=memory
DATABASE_URL=postgresql://qaagent:qaagent@localhost:5432/qaagent
PAPER_STORAGE_DIR=storage/pdfs
OPENALEX_MAILTO=
CROSSREF_MAILTO=
SEMANTIC_SCHOLAR_API_KEY=
```

默认 `STORAGE_BACKEND=memory`，不需要数据库即可试用。重启后内存中的论文元数据和问答记录会丢失，但 `storage/pdfs/` 中的 PDF 文件仍会保留。

## 5. 启动后端

```powershell
cd apps/api
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
```

正常返回：

```json
{"status":"ok"}
```

## 6. 启动前端

另开一个终端：

```powershell
cd apps/web
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

浏览器访问：

```text
http://127.0.0.1:3000
```

## 7. 搜索论文

1. 在左侧搜索框输入论文标题、关键词、DOI 或研究主题。
2. 选择检索源：
   - `All sources`：同时搜索所有开放源。
   - `OpenAlex`：广覆盖元数据搜索。
   - `Semantic Scholar`：引用、摘要和开放 PDF 信息。
   - `Crossref`：DOI 元数据校验。
   - `arXiv`：预印本和 arXiv PDF。
3. 可选填写起止年份。
4. 勾选 `PDF only` 可只看带 PDF 链接的结果。
5. 点击搜索按钮。
6. 搜索框下方会显示每个 source 的成功或失败状态。
7. 点击结果卡片中的 `Import` 导入论文。

搜索调用的是真实外部 API，不是 mock 数据。

## 8. 上传本地 PDF

1. 在左侧 `Upload PDF` 区域选择 PDF 文件。
2. 可选填写论文标题。
3. 点击 `Upload`。
4. 系统会保存 PDF、解析页面和文本块，并建立检索索引。

上传后前端会兜底刷新论文详情，避免缺少 `pages` 字段导致页面崩溃。

## 9. 阅读 PDF

中间 PDF 阅读器支持：

- 上一页、下一页
- 放大、缩小
- 显示当前页码
- 点击问答证据后自动跳到对应页
- 高亮证据文本块的大致位置

## 10. 配置 LLM

点击右上角设置按钮打开 `LLM Settings`。

可配置：

- Provider
- Model
- Custom model
- Base URL
- API Key
- Azure API version
- Temperature
- Max tokens

API Key 只保存在浏览器 `localStorage`，每次提问时随请求临时发送给后端。后端不会保存 API Key，也不会把它写入数据库。

支持的服务商：

- OpenAI
- Azure OpenAI
- Anthropic Claude
- Google Gemini
- DeepSeek
- Qwen / DashScope
- Moonshot / Kimi
- Zhipu GLM
- OpenRouter
- Ollama / Local
- Custom OpenAI-compatible endpoint

如果没有配置可用 LLM，系统会使用本地降级回答，只根据检索片段整理证据摘要。

`.env` 中的 `OPENAI_API_KEY` 和 `OPENAI_CHAT_MODEL` 仍可作为服务端开发兜底配置。

## 11. 向论文提问

1. 确认当前论文状态为 `ready`。
2. 在右侧问答框输入问题。
3. 点击 `Ask`。
4. 系统会检索 PDF 中相关文本块，并生成回答。
5. 回答下方会显示引用证据，包括页码、相关片段和检索分数。
6. 点击证据卡片可跳转到 PDF 对应页。

安全边界：

- 默认不会把整篇 PDF 发送给模型。
- 只发送检索到的 top chunks。
- PDF 文本被视为不可信输入，不会执行 PDF 中的指令。
- 如果 PDF 中没有足够证据，系统会提示无法从当前论文判断。

## 12. 使用 PostgreSQL + pgvector

启动数据库和 Redis：

```powershell
docker compose up -d db redis
```

修改 `.env`：

```env
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://qaagent:qaagent@localhost:5432/qaagent
```

然后重启后端。

数据库结构在：

```text
infra/init.sql
```

核心表包括：

- `papers`
- `paper_sources`
- `pdf_assets`
- `pdf_pages`
- `text_chunks`
- `qa_sessions`
- `qa_messages`

## 13. API 速查

搜索论文：

```http
GET /api/papers/search?q=rag&source=all&has_pdf=true&limit=12
```

导入论文：

```http
POST /api/papers/import
```

上传 PDF：

```http
POST /api/papers/upload
```

获取论文详情：

```http
GET /api/papers/{paper_id}
```

向论文提问：

```http
POST /api/papers/{paper_id}/ask
```

获取 LLM 模板：

```http
GET /api/settings/llm/providers
```

测试 LLM 连接：

```http
POST /api/llm/test
```

API 文档页面：

```text
http://127.0.0.1:8000/docs
```

## 14. 验证命令

后端：

```powershell
cd apps/api
python -m compileall app tests
python -m pytest
```

前端：

```powershell
cd apps/web
npm run build
npm run lint
```

当前实现已验证：

- 后端测试：13 passed
- 前端构建：通过
- 前端 lint：通过

## 15. 常见问题

### 搜索失败怎么办？

开放论文源可能出现网络、限流或临时不可用。现在页面会显示每个 source 的状态。你可以换一个 source、使用 DOI/arXiv ID 搜索，或直接上传本地 PDF。

### 上传后页面崩溃怎么办？

这个问题已修复。后端现在返回 `PaperDetail`，前端也会对 `pages` 和 `chunks_count` 做默认值防护，并在上传/导入后刷新论文详情。

### 为什么回答像摘要？

没有配置 LLM 时，系统使用本地降级回答。打开右上角设置面板并填写可用 API Key 后，回答会由你选择的模型生成。

### npm audit 有安全提示怎么办？

当前本地环境是 Node.js 16，所以前端锁定了兼容 Node 16 的 Next.js 13 和 PDF.js 2。生产部署前建议升级到 Node.js 20+，然后升级 Next.js 和 PDF.js 到当前安全版本。

## 16. 当前限制

- 这是 MVP，不包含登录、多租户、权限、计费。
- 默认内存存储重启后会丢失论文元数据和问答记录。
- PDF 表格、公式和图片理解仍是基础能力。
- 扫描版 PDF 如果没有文本层，当前不会自动 OCR。
- Google Scholar 未接入，避免封禁和合规风险。
