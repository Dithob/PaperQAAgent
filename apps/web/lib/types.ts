export type ParseStatus = "metadata_only" | "queued" | "parsing" | "ready" | "failed";

export type SourceIds = {
  openalex?: string | null;
  semantic_scholar?: string | null;
  crossref?: string | null;
  arxiv?: string | null;
  doi?: string | null;
};

export type BoundingBox = {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  page_width: number;
  page_height: number;
};

export type PaperSearchResult = {
  title: string;
  authors: string[];
  year?: number | null;
  venue?: string | null;
  doi?: string | null;
  abstract?: string | null;
  pdf_url?: string | null;
  citation_count?: number | null;
  source_ids: SourceIds;
  sources: string[];
  url?: string | null;
};

export type SourceStatus = {
  source: string;
  ok: boolean;
  count: number;
  error?: string | null;
  elapsed_ms?: number | null;
};

export type SearchPayload = {
  results: PaperSearchResult[];
  sources_status: SourceStatus[];
};

export type Paper = {
  id: string;
  title: string;
  authors: string[];
  year?: number | null;
  venue?: string | null;
  doi?: string | null;
  abstract?: string | null;
  pdf_url?: string | null;
  pdf_path?: string | null;
  parse_status: ParseStatus;
  source_ids: SourceIds;
  created_at: string;
  updated_at: string;
};

export type PdfAsset = {
  id: string;
  paper_id: string;
  original_filename?: string | null;
  storage_path: string;
  sha256?: string | null;
  byte_size?: number | null;
  created_at: string;
};

export type PdfPage = {
  id: string;
  paper_id: string;
  page_number: number;
  width: number;
  height: number;
  text: string;
  created_at: string;
};

export type TextChunk = {
  id: string;
  paper_id: string;
  page_number: number;
  section?: string | null;
  bbox?: BoundingBox | null;
  text: string;
  token_count: number;
  score?: number | null;
  created_at: string;
};

export type PaperDetail = Paper & {
  pdf_asset?: PdfAsset | null;
  pages: PdfPage[];
  chunks_count: number;
  sections: string[];
};

export type Citation = {
  chunk_id: string;
  page_number: number;
  bbox?: BoundingBox | null;
  text: string;
  score?: number | null;
};

export type AskPaperResponse = {
  answer: string;
  citations: Citation[];
  confidence: number;
  abstained: boolean;
  session_id?: string | null;
  provider?: string | null;
  model?: string | null;
  usage?: Record<string, unknown> | null;
  finish_reason?: string | null;
};

export type ReasoningLevel = "fast" | "balanced" | "deep";

export type AgentScope = "current_paper";

export type AgentEventType =
  | "run_started"
  | "tool_started"
  | "tool_finished"
  | "token"
  | "final"
  | "error";

export type AgentRunStep = {
  name: string;
  status: "running" | "succeeded" | "failed";
  detail?: string | null;
};

export type AgentChatEvent = {
  event: AgentEventType;
  run_id?: string | null;
  session_id?: string | null;
  payload: Record<string, unknown>;
};

export type AgentChatRequest = {
  session_id?: string | null;
  paper_id: string;
  message: string;
  scope: AgentScope;
  reasoning_level: ReasoningLevel;
  strict_citations: boolean;
  top_k?: number | null;
  llm_config?: LLMConfig | null;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  confidence?: number;
  provider?: string | null;
  model?: string | null;
  steps?: AgentRunStep[];
  pending?: boolean;
};

export type AgentSession = {
  id: string;
  paper_id: string;
  title?: string | null;
  created_at: string;
};

export type LLMProviderId =
  | "openai"
  | "azure_openai"
  | "anthropic"
  | "gemini"
  | "deepseek"
  | "qwen"
  | "moonshot"
  | "zhipu"
  | "openrouter"
  | "ollama"
  | "custom_openai";

export type ModelOption = {
  id: string;
  label: string;
};

export type LLMProviderTemplate = {
  id: LLMProviderId;
  label: string;
  base_url?: string | null;
  api_key_required: boolean;
  api_key_label: string;
  models: ModelOption[];
  default_model: string;
  supports_custom_base_url: boolean;
};

export type LLMConfig = {
  provider: LLMProviderId;
  model: string;
  api_key?: string | null;
  base_url?: string | null;
  api_version?: string | null;
  options: {
    temperature: number;
    max_tokens: number;
  };
};

export type LLMTestResponse = {
  ok: boolean;
  provider: LLMProviderId;
  model: string;
  message: string;
};
