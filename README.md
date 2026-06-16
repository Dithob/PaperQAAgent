# PaperQAAgent

PaperQAAgent is a small-group research assistant for searching papers, importing or uploading PDFs, reading them with page-level evidence, and asking citation-grounded questions.

中文使用手册见 [docs/USAGE.zh-CN.md](docs/USAGE.zh-CN.md).

## What Is Implemented

- `apps/api`: FastAPI service with paper search adapters for OpenAlex, Semantic Scholar, Crossref, and arXiv.
- Source-level search status, timeout retry, lightweight search cache, and PDF-only filtering.
- PDF import/upload, local PDF storage, PyMuPDF-based text and bounding-box extraction.
- Chunk indexing with deterministic local embeddings and keyword reranking.
- Citation-grounded question answering with local fallback and per-request LLM provider config.
- Multi-provider LLM templates: OpenAI, Azure OpenAI, Anthropic, Gemini, DeepSeek, Qwen, Moonshot/Kimi, Zhipu, OpenRouter, Ollama, and custom OpenAI-compatible endpoints.
- `apps/web`: Next.js research workspace with search, import, upload, PDF.js rendering, settings panel, question answering, and evidence navigation.
- `infra/init.sql`: PostgreSQL + pgvector schema matching the planned data model.

## Local Development

1. Copy `.env.example` to `.env` and fill optional metadata API settings.
2. Start the database if you want Postgres:

```powershell
docker compose up -d db redis
```

3. Install and run the API:

```powershell
cd apps/api
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

4. Install and run the web app:

```powershell
cd apps/web
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

The web app runs at `http://127.0.0.1:3000`, and the API runs at `http://127.0.0.1:8000`.

## LLM Configuration

The web app has a settings panel. API keys are stored in the browser's `localStorage` and sent to the API only for the current question. They are not persisted by the backend.

If no provider is configured, QAAgent uses a local evidence-summary fallback. `.env` still supports `OPENAI_API_KEY` and `OPENAI_CHAT_MODEL` as a server-side fallback for local development.

## Production Dependency Note

This workspace was verified on the available local Node.js 16 runtime, so the web app uses Next.js 13 and PDF.js 2 for development compatibility. `npm audit --omit=dev` reports production advisories for those legacy packages. Before deploying beyond local/small-group evaluation, upgrade the runtime to Node.js 20+ and move Next.js/PDF.js to current patched major versions.

## Storage Modes

`STORAGE_BACKEND=memory` is the default so the project can run without a database during early development. Set `STORAGE_BACKEND=postgres` with `DATABASE_URL` to use the schema in `infra/init.sql`.

## API Surface

- `GET /api/papers/search?q=&year_from=&year_to=&source=&has_pdf=&limit=`
- `POST /api/papers/import`
- `POST /api/papers/upload`
- `GET /api/papers/{paper_id}`
- `POST /api/papers/{paper_id}/ask`
- `GET /api/papers/{paper_id}/chunks?query=`
- `GET /api/settings/llm/providers`
- `POST /api/llm/test`

PDF text is treated as untrusted evidence. The answerer sends only retrieved passages to an LLM provider; it never sends the full PDF by default.
