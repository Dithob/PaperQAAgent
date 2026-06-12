CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS papers (
  id UUID PRIMARY KEY,
  title TEXT NOT NULL,
  authors JSONB NOT NULL DEFAULT '[]'::jsonb,
  abstract TEXT,
  year INTEGER,
  venue TEXT,
  doi TEXT,
  pdf_url TEXT,
  pdf_path TEXT,
  parse_status TEXT NOT NULL DEFAULT 'metadata_only',
  source_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS papers_doi_unique_idx
  ON papers (lower(doi))
  WHERE doi IS NOT NULL AND doi <> '';

CREATE INDEX IF NOT EXISTS papers_title_trgm_idx ON papers USING gin (title gin_trgm_ops);

CREATE TABLE IF NOT EXISTS paper_sources (
  id UUID PRIMARY KEY,
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS pdf_assets (
  id UUID PRIMARY KEY,
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  original_filename TEXT,
  storage_path TEXT NOT NULL,
  sha256 TEXT,
  byte_size BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pdf_pages (
  id UUID PRIMARY KEY,
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  width DOUBLE PRECISION NOT NULL,
  height DOUBLE PRECISION NOT NULL,
  text TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (paper_id, page_number)
);

CREATE TABLE IF NOT EXISTS text_chunks (
  id UUID PRIMARY KEY,
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  section TEXT,
  bbox JSONB,
  text TEXT NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0,
  embedding vector(384),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS text_chunks_paper_idx ON text_chunks (paper_id);
CREATE INDEX IF NOT EXISTS text_chunks_text_trgm_idx ON text_chunks USING gin (text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS text_chunks_embedding_idx
  ON text_chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 64);

CREATE TABLE IF NOT EXISTS qa_sessions (
  id UUID PRIMARY KEY,
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  title TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS qa_messages (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES qa_sessions(id) ON DELETE CASCADE,
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  citations JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id UUID PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES qa_sessions(id) ON DELETE CASCADE,
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'running',
  reasoning_level TEXT NOT NULL DEFAULT 'balanced',
  strict_citations BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  error TEXT
);

CREATE INDEX IF NOT EXISTS agent_runs_session_idx ON agent_runs (session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_run_steps (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',
  detail TEXT,
  elapsed_ms INTEGER,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_run_steps_run_idx ON agent_run_steps (run_id, created_at);
