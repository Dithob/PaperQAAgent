"use client";

import {
  Bot,
  CheckCircle2,
  FileUp,
  Loader2,
  MessageSquare,
  Send,
  Settings,
  Target,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { listAgentMessages, listAgentSessions, streamAgentChat, uploadPaper } from "../lib/api";
import type {
  AgentChatEvent,
  AgentRunStep,
  AskPaperResponse,
  ChatMessage,
  Citation,
  LLMConfig,
  PaperDetail,
  ReasoningLevel,
} from "../lib/types";

type Props = {
  paper: PaperDetail | null;
  llmConfig: LLMConfig | null;
  activeCitationId?: string | null;
  onCitationSelected: (citation: Citation) => void;
  onPaperSelected: (paper: PaperDetail) => void;
  onOpenSettings: () => void;
  onNotice: (message: string) => void;
};

export function AgentChat({
  paper,
  llmConfig,
  activeCitationId,
  onCitationSelected,
  onPaperSelected,
  onOpenSettings,
  onNotice,
}: Props) {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [reasoningLevel, setReasoningLevel] = useState<ReasoningLevel>("balanced");
  const [strictCitations, setStrictCitations] = useState(true);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const paperId = paper?.id || null;

  useEffect(() => {
    setMessages([]);
    setSessionId(null);
    if (!paperId) return;
    let cancelled = false;
    listAgentSessions(paperId)
      .then(async (sessions) => {
        if (cancelled || !sessions[0]) return;
        setSessionId(sessions[0].id);
        const history = await listAgentMessages(sessions[0].id);
        if (!cancelled) setMessages(history);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [paperId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const clean = message.trim();
    if (!paper) {
      onNotice("请先搜索或上传一篇论文。");
      return;
    }
    if (paper.parse_status !== "ready") {
      onNotice(`当前论文还不能问答，解析状态：${paper.parse_status}`);
      return;
    }
    if (!clean || loading) return;

    setMessage("");
    setLoading(true);
    const pendingIndex = messages.length + 1;
    setMessages((current) => [
      ...current,
      { role: "user", content: clean },
      { role: "assistant", content: "", steps: [], pending: true },
    ]);

    try {
      await streamAgentChat(
        {
          session_id: sessionId,
          paper_id: paper.id,
          message: clean,
          scope: "current_paper",
          reasoning_level: reasoningLevel,
          strict_citations: strictCitations,
          llm_config: llmConfig || undefined,
        },
        (event) => handleAgentEvent(event, pendingIndex)
      );
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Agent request failed.";
      onNotice(detail);
      updatePending(pendingIndex, { content: detail, pending: false });
    } finally {
      setLoading(false);
    }
  }

  function handleAgentEvent(event: AgentChatEvent, pendingIndex: number) {
    if (event.session_id) setSessionId(event.session_id);
    if (event.event === "tool_started" || event.event === "tool_finished") {
      const name = String(event.payload.name || "tool");
      const detail = String(event.payload.detail || "");
      const status = event.event === "tool_finished" ? "succeeded" : "running";
      appendOrUpdateStep(pendingIndex, { name, detail, status });
    }
    if (event.event === "final") {
      const response = event.payload as unknown as AskPaperResponse;
      updatePending(pendingIndex, {
        content: response.answer || "",
        citations: response.citations || [],
        confidence: response.confidence,
        provider: response.provider,
        model: response.model,
        pending: false,
      });
      if (response.citations?.[0]) onCitationSelected(response.citations[0]);
    }
    if (event.event === "error") {
      updatePending(pendingIndex, {
        content: String(event.payload.message || "Agent failed."),
        pending: false,
      });
    }
  }

  function appendOrUpdateStep(index: number, step: AgentRunStep) {
    setMessages((current) => current.map((item, itemIndex) => {
      if (itemIndex !== index) return item;
      const steps = item.steps || [];
      const existing = steps.findIndex((candidate) => candidate.name === step.name);
      const nextSteps = existing >= 0
        ? steps.map((candidate, stepIndex) => stepIndex === existing ? { ...candidate, ...step } : candidate)
        : [...steps, step];
      return { ...item, steps: nextSteps };
    }));
  }

  function updatePending(index: number, patch: Partial<ChatMessage>) {
    setMessages((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...patch } : item
    )));
  }

  async function handleComposerUpload(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.set("file", file);
      form.set("parse_immediately", "true");
      const nextPaper = await uploadPaper(form);
      onPaperSelected(nextPaper);
      onNotice("PDF 已上传并解析，可以开始提问。");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const modelLabel = llmConfig ? `${llmConfig.provider}/${llmConfig.model}` : "Local fallback";

  return (
    <main className="pane agent-pane">
      <div className="agent-thread">
        <div className="agent-header">
          <div>
            <p className="section-title">Paper Agent</p>
            <h1>{paper?.title || "上传或导入论文后开始对话"}</h1>
          </div>
          <span className={`status-badge ${paper?.parse_status || ""}`}>
            <CheckCircle2 size={14} />
            {paper?.parse_status || "no paper"}
          </span>
        </div>

        <div className="agent-messages">
          {messages.length === 0 ? (
            <div className="agent-empty">
              <Bot size={28} />
              <div>
                <h2>围绕当前论文提问</h2>
                <p>Agent 会先检索论文片段，整理证据，再调用你选择的模型回答，并把结论绑定到页码和 PDF 坐标。</p>
              </div>
            </div>
          ) : null}
          {messages.map((item, index) => (
            <article className={`message agent-message ${item.role}`} key={`${item.role}-${index}`}>
              <div className="paper-meta">
                {item.role === "user" ? <MessageSquare size={14} /> : <Bot size={14} />}
                {item.role === "user" ? "You" : assistantLabel(item)}
              </div>
              {item.steps?.length ? (
                <div className="run-steps">
                  {item.steps.map((step) => (
                    <span className={`run-step ${step.status}`} key={step.name} title={step.detail || undefined}>
                      {step.status === "running" ? <Loader2 size={13} /> : <CheckCircle2 size={13} />}
                      {step.name}
                    </span>
                  ))}
                </div>
              ) : null}
              {item.content ? <div className="answer-text">{item.content}</div> : null}
              {item.pending && !item.content ? <div className="small-muted">Agent 正在阅读证据...</div> : null}
              {item.citations?.length ? (
                <div className="evidence-list">
                  {item.citations.map((citation) => (
                    <button
                      className={`evidence-card ${activeCitationId === citation.chunk_id ? "active" : ""}`}
                      key={citation.chunk_id}
                      onClick={() => onCitationSelected(citation)}
                    >
                      <div className="paper-meta">
                        <Target size={14} /> Page {citation.page_number} · score {citation.score?.toFixed(3) ?? "-"}
                      </div>
                      <div className="small-muted">{trim(citation.text, 260)}</div>
                    </button>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
        </div>

        <form className="agent-composer" onSubmit={submit}>
          <textarea
            className="textarea composer-input"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="询问这篇论文的方法、实验、结论、局限或某个公式/段落..."
            disabled={loading}
          />
          <div className="composer-toolbar">
            <button type="button" className="secondary-button model-button" onClick={onOpenSettings}>
              <Settings size={15} />
              {modelLabel}
            </button>
            <select
              className="select compact-select"
              value={reasoningLevel}
              onChange={(event) => setReasoningLevel(event.target.value as ReasoningLevel)}
            >
              <option value="fast">Fast</option>
              <option value="balanced">Balanced</option>
              <option value="deep">Deep</option>
            </select>
            <select className="select compact-select" value="current_paper" disabled>
              <option value="current_paper">Current paper</option>
            </select>
            <label className="check-row compact-check">
              <input
                type="checkbox"
                checked={strictCitations}
                onChange={(event) => setStrictCitations(event.target.checked)}
              />
              <span>Strict citations</span>
            </label>
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={(event) => handleComposerUpload(event.target.files)}
            />
            <button
              type="button"
              className="icon-button secondary-button"
              title="Upload PDF"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? <Loader2 size={16} /> : <FileUp size={16} />}
            </button>
            <button className="primary-button send-button" disabled={!paper || loading || !message.trim()}>
              {loading ? <Loader2 size={16} /> : <Send size={16} />}
              Send
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}

function assistantLabel(message: ChatMessage) {
  const confidence = typeof message.confidence === "number" ? ` · ${(message.confidence * 100).toFixed(0)}%` : "";
  const model = message.model ? ` · ${message.provider || "llm"}/${message.model}` : "";
  return `Agent${confidence}${model}`;
}

function trim(text: string, max: number) {
  return text.length <= max ? text : `${text.slice(0, max - 3)}...`;
}
