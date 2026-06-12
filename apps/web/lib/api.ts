import type {
  AgentChatEvent,
  AgentChatRequest,
  AgentSession,
  AskPaperResponse,
  ChatMessage,
  LLMConfig,
  LLMProviderTemplate,
  LLMTestResponse,
  PaperDetail,
  PaperSearchResult,
  SearchPayload
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function parseJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload as T;
}

export async function searchPapers(params: {
  q: string;
  source: string;
  yearFrom?: string;
  yearTo?: string;
  hasPdf?: boolean;
  limit?: number;
}): Promise<SearchPayload> {
  const searchParams = new URLSearchParams({
    q: params.q,
    source: params.source,
    limit: String(params.limit || 12)
  });
  if (params.yearFrom) searchParams.set("year_from", params.yearFrom);
  if (params.yearTo) searchParams.set("year_to", params.yearTo);
  if (params.hasPdf !== undefined) searchParams.set("has_pdf", String(params.hasPdf));
  const response = await fetch(`${API_URL}/api/papers/search?${searchParams.toString()}`);
  const payload = await parseJson<SearchPayload>(response);
  return {
    results: payload.results || [],
    sources_status: payload.sources_status || []
  };
}

export async function importPaper(result: PaperSearchResult): Promise<PaperDetail> {
  const response = await fetch(`${API_URL}/api/papers/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doi: result.doi,
      arxiv_id: result.source_ids?.arxiv,
      semantic_scholar_id: result.source_ids?.semantic_scholar,
      openalex_id: result.source_ids?.openalex,
      pdf_url: result.pdf_url,
      title: result.title,
      authors: result.authors,
      year: result.year,
      venue: result.venue,
      abstract: result.abstract,
      parse_immediately: true
    })
  });
  const payload = await parseJson<{ paper: PaperDetail }>(response);
  const paper = hydratePaperDetail(payload.paper);
  return getPaper(paper.id).catch(() => paper);
}

export async function uploadPaper(form: FormData): Promise<PaperDetail> {
  const response = await fetch(`${API_URL}/api/papers/upload`, {
    method: "POST",
    body: form
  });
  const payload = await parseJson<{ paper: PaperDetail }>(response);
  const paper = hydratePaperDetail(payload.paper);
  return getPaper(paper.id).catch(() => paper);
}

export async function getPaper(id: string): Promise<PaperDetail> {
  const response = await fetch(`${API_URL}/api/papers/${id}`);
  return hydratePaperDetail(await parseJson<PaperDetail>(response));
}

export async function askPaper(id: string, question: string, llmConfig?: LLMConfig | null): Promise<AskPaperResponse> {
  const response = await fetch(`${API_URL}/api/papers/${id}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      top_k: 6,
      llm_config: llmConfig || undefined
    })
  });
  return parseJson<AskPaperResponse>(response);
}

export async function streamAgentChat(
  payload: AgentChatRequest,
  onEvent: (event: AgentChatEvent) => void
): Promise<void> {
  const response = await fetch(`${API_URL}/api/agent/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      llm_config: payload.llm_config || undefined
    })
  });
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(detail || response.statusText);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const event = parseSseEvent(part);
      if (event) onEvent(event);
    }
  }
  if (buffer.trim()) {
    const event = parseSseEvent(buffer);
    if (event) onEvent(event);
  }
}

export async function listAgentSessions(paperId: string): Promise<AgentSession[]> {
  const response = await fetch(`${API_URL}/api/agent/sessions?paper_id=${encodeURIComponent(paperId)}`);
  return parseJson<AgentSession[]>(response);
}

export async function listAgentMessages(sessionId: string): Promise<ChatMessage[]> {
  const response = await fetch(`${API_URL}/api/agent/sessions/${sessionId}/messages`);
  const payload = await parseJson<Array<ChatMessage & { citations?: unknown }>>(response);
  return payload.map((message) => ({
    role: message.role,
    content: message.content,
    citations: Array.isArray(message.citations) ? message.citations as never : []
  }));
}

export async function getLlmProviderTemplates(): Promise<LLMProviderTemplate[]> {
  const response = await fetch(`${API_URL}/api/settings/llm/providers`);
  return parseJson<LLMProviderTemplate[]>(response);
}

export async function testLlmConfig(config: LLMConfig): Promise<LLMTestResponse> {
  const response = await fetch(`${API_URL}/api/llm/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config)
  });
  return parseJson<LLMTestResponse>(response);
}

export function pdfFileUrl(paper: PaperDetail | null): string | null {
  if (!paper?.pdf_asset) return null;
  const filename = paper.pdf_asset.storage_path.split(/[\\/]/).pop();
  return filename ? `${API_URL}/files/pdfs/${encodeURIComponent(filename)}` : null;
}

export function hydratePaperDetail(paper: PaperDetail): PaperDetail {
  return {
    ...paper,
    authors: paper.authors || [],
    pages: paper.pages || [],
    chunks_count: paper.chunks_count || 0,
    sections: paper.sections || []
  };
}

function parseSseEvent(raw: string): AgentChatEvent | null {
  const dataLine = raw.split("\n").find((line) => line.startsWith("data: "));
  if (!dataLine) return null;
  try {
    return JSON.parse(dataLine.slice(6)) as AgentChatEvent;
  } catch {
    return null;
  }
}
