from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


ParseStatus = Literal["metadata_only", "queued", "parsing", "ready", "failed"]
PaperSource = Literal["openalex", "semantic_scholar", "crossref", "arxiv", "upload", "pdf_url"]
ReasoningLevel = Literal["fast", "balanced", "deep"]
AgentScope = Literal["current_paper"]
AgentEventType = Literal[
    "run_started",
    "tool_started",
    "tool_finished",
    "token",
    "final",
    "error",
]
AgentRunStatus = Literal["running", "succeeded", "failed"]


class SourceIds(BaseModel):
    openalex: str | None = None
    semantic_scholar: str | None = None
    crossref: str | None = None
    arxiv: str | None = None
    doi: str | None = None


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float
    page_height: float


class PaperSearchResult(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    pdf_url: str | None = None
    citation_count: int | None = None
    source_ids: SourceIds = Field(default_factory=SourceIds)
    sources: list[PaperSource] = Field(default_factory=list)
    url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class SourceStatus(BaseModel):
    source: str
    ok: bool
    count: int = 0
    error: str | None = None
    elapsed_ms: int | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[PaperSearchResult]
    sources_status: list[SourceStatus] = Field(default_factory=list)


class Paper(BaseModel):
    id: UUID
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    pdf_url: str | None = None
    pdf_path: str | None = None
    parse_status: ParseStatus = "metadata_only"
    source_ids: SourceIds = Field(default_factory=SourceIds)
    created_at: datetime
    updated_at: datetime


class PdfAsset(BaseModel):
    id: UUID
    paper_id: UUID
    original_filename: str | None = None
    storage_path: str
    sha256: str | None = None
    byte_size: int | None = None
    created_at: datetime


class PdfPage(BaseModel):
    id: UUID
    paper_id: UUID
    page_number: int
    width: float
    height: float
    text: str
    created_at: datetime


class TextChunk(BaseModel):
    id: UUID
    paper_id: UUID
    page_number: int
    section: str | None = None
    bbox: BoundingBox | None = None
    text: str
    token_count: int
    score: float | None = None
    created_at: datetime


class PaperDetail(Paper):
    pdf_asset: PdfAsset | None = None
    pages: list[PdfPage] = Field(default_factory=list)
    chunks_count: int = 0
    sections: list[str] = Field(default_factory=list)


class ImportPaperRequest(BaseModel):
    doi: str | None = None
    arxiv_id: str | None = None
    semantic_scholar_id: str | None = None
    openalex_id: str | None = None
    pdf_url: HttpUrl | None = None
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    parse_immediately: bool = True


class ImportPaperResponse(BaseModel):
    paper: PaperDetail
    imported_pdf: bool
    message: str


LLMProviderId = Literal[
    "openai",
    "azure_openai",
    "anthropic",
    "gemini",
    "deepseek",
    "qwen",
    "moonshot",
    "zhipu",
    "openrouter",
    "ollama",
    "custom_openai",
]


class ModelOption(BaseModel):
    id: str
    label: str


class LLMProviderTemplate(BaseModel):
    id: LLMProviderId
    label: str
    base_url: str | None = None
    api_key_required: bool = True
    api_key_label: str = "API key"
    models: list[ModelOption] = Field(default_factory=list)
    default_model: str
    supports_custom_base_url: bool = False


class LLMOptions(BaseModel):
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=900, ge=128, le=8000)


class LLMConfig(BaseModel):
    provider: LLMProviderId = "openai"
    model: str
    api_key: str | None = None
    base_url: str | None = None
    api_version: str | None = None
    options: LLMOptions = Field(default_factory=LLMOptions)


class LLMTestResponse(BaseModel):
    ok: bool
    provider: LLMProviderId
    model: str
    message: str


class AskPaperRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    session_id: UUID | None = None
    top_k: int = Field(default=6, ge=1, le=12)
    llm_config: LLMConfig | None = None


class Citation(BaseModel):
    chunk_id: UUID
    page_number: int
    bbox: BoundingBox | None = None
    text: str
    score: float | None = None


class AskPaperResponse(BaseModel):
    answer: str
    citations: list[Citation]
    confidence: float = Field(ge=0, le=1)
    abstained: bool
    session_id: UUID | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    model_config = ConfigDict(json_schema_extra={"examples": []})


class AgentSession(BaseModel):
    id: UUID
    paper_id: UUID
    title: str | None = None
    created_at: datetime


class AgentMessage(BaseModel):
    id: UUID
    session_id: UUID | None = None
    paper_id: UUID
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class AgentRun(BaseModel):
    id: UUID
    session_id: UUID
    paper_id: UUID
    status: AgentRunStatus = "running"
    reasoning_level: ReasoningLevel = "balanced"
    strict_citations: bool = True
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class AgentRunStep(BaseModel):
    id: UUID
    run_id: UUID
    name: str
    status: AgentRunStatus = "running"
    detail: str | None = None
    elapsed_ms: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EvidenceItem(BaseModel):
    chunk_id: UUID
    page_number: int
    section: str | None = None
    bbox: BoundingBox | None = None
    text: str
    score: float | None = None


class EvidencePacket(BaseModel):
    paper_id: UUID
    question: str
    items: list[EvidenceItem] = Field(default_factory=list)


class AgentChatRequest(BaseModel):
    session_id: UUID | None = None
    paper_id: UUID
    message: str = Field(min_length=2, max_length=4000)
    scope: AgentScope = "current_paper"
    reasoning_level: ReasoningLevel = "balanced"
    strict_citations: bool = True
    top_k: int | None = Field(default=None, ge=1, le=12)
    llm_config: LLMConfig | None = None


class AgentChatEvent(BaseModel):
    event: AgentEventType
    run_id: UUID | None = None
    session_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
