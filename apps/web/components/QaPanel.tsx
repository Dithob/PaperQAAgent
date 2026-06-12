"use client";

import { Bot, Loader2, MessageSquare, Send, Target } from "lucide-react";
import { FormEvent, useState } from "react";
import { askPaper } from "../lib/api";
import type { ChatMessage, Citation, LLMConfig, PaperDetail } from "../lib/types";

type Props = {
  paper: PaperDetail | null;
  llmConfig: LLMConfig | null;
  activeCitationId?: string | null;
  onCitationSelected: (citation: Citation) => void;
  onNotice: (message: string) => void;
};

export function QaPanel({ paper, llmConfig, activeCitationId, onCitationSelected, onNotice }: Props) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);

  async function submitQuestion(event: FormEvent) {
    event.preventDefault();
    if (!paper) {
      onNotice("Select a parsed paper first.");
      return;
    }
    if (!question.trim()) return;
    const asked = question.trim();
    setQuestion("");
    setMessages((current) => [...current, { role: "user", content: asked }]);
    setLoading(true);
    try {
      const response = await askPaper(paper.id, asked, llmConfig);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: response.answer,
          citations: response.citations || [],
          confidence: response.confidence,
          provider: response.provider,
          model: response.model
        }
      ]);
      if (response.citations?.[0]) onCitationSelected(response.citations[0]);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Question failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <aside className="pane qa-pane">
      <div className="pane-scroll">
        <div className="pane-inner">
          <p className="section-title">Ask This Paper</p>
          <form className="qa-form" onSubmit={submitQuestion}>
            <textarea
              className="textarea"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask about the method, assumptions, experiments, or limitations."
              disabled={!paper || loading}
            />
            <button className="primary-button" disabled={!paper || loading || paper.parse_status !== "ready"}>
              {loading ? <Loader2 size={16} /> : <Send size={16} />}
              Ask
            </button>
          </form>

          <div className="messages">
            {messages.length === 0 ? (
              <div className="message assistant">
                <div className="paper-meta"><Bot size={14} /> Evidence-grounded answers will appear here.</div>
              </div>
            ) : null}
            {messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="paper-meta">
                  {message.role === "user" ? <MessageSquare size={14} /> : <Bot size={14} />}
                  {" "}
                  {message.role === "user" ? "You" : assistantLabel(message)}
                </div>
                <div className="answer-text">{message.content}</div>
                {message.citations?.length ? (
                  <div className="evidence-list">
                    {message.citations.map((citation) => (
                      <button
                        className={`evidence-card ${activeCitationId === citation.chunk_id ? "active" : ""}`}
                        key={citation.chunk_id}
                        onClick={() => onCitationSelected(citation)}
                      >
                        <div className="paper-meta"><Target size={14} /> Page {citation.page_number} · score {citation.score?.toFixed(3) ?? "-"}</div>
                        <div className="small-muted">{trim(citation.text, 260)}</div>
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}

function assistantLabel(message: ChatMessage) {
  const confidence = message.confidence ? ` · ${(message.confidence * 100).toFixed(0)}%` : "";
  const model = message.model ? ` · ${message.provider || "llm"}/${message.model}` : "";
  return `Agent${confidence}${model}`;
}

function trim(text: string, max: number) {
  return text.length <= max ? text : `${text.slice(0, max - 3)}...`;
}
