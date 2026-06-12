from __future__ import annotations

import time
from collections.abc import AsyncIterator
from uuid import UUID

from app.core.config import Settings
from app.models.schemas import (
    AgentChatEvent,
    AgentChatRequest,
    AgentMessage,
    AgentSession,
    AskPaperResponse,
    LLMConfig,
    PaperDetail,
)
from app.services.citation_verifier import CitationVerifier
from app.services.evidence_builder import EvidenceBuilder, evidence_to_citations
from app.services.llm_providers import answer_with_evidence
from app.services.retrieval import RetrievalService
from app.services.storage import PaperRepository


class PaperChatAgent:
    def __init__(self, settings: Settings, repository: PaperRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.retrieval = RetrievalService(repository)
        self.evidence_builder = EvidenceBuilder()
        self.citation_verifier = CitationVerifier()

    async def stream(self, request: AgentChatRequest) -> AsyncIterator[AgentChatEvent]:
        session = await self._session_for_request(request)
        paper = await self.repository.get_paper(request.paper_id)
        if not paper:
            yield AgentChatEvent(
                event="error",
                session_id=session.id,
                payload={"message": "Paper not found."},
            )
            return

        run = await self.repository.create_agent_run(
            session.id,
            paper.id,
            request.reasoning_level,
            request.strict_citations,
        )
        yield AgentChatEvent(
            event="run_started",
            run_id=run.id,
            session_id=session.id,
            payload={
                "paper_id": str(paper.id),
                "reasoning_level": request.reasoning_level,
                "strict_citations": request.strict_citations,
            },
        )

        try:
            if paper.parse_status != "ready":
                message = f"当前论文还不能问答，解析状态是 {paper.parse_status}。请等待解析完成或重新上传 PDF。"
                await self.repository.add_qa_message(paper.id, "user", request.message, [], session.id)
                await self.repository.add_qa_message(paper.id, "assistant", message, [], session.id)
                await self.repository.complete_agent_run(run.id, "failed", message)
                yield AgentChatEvent(
                    event="error",
                    run_id=run.id,
                    session_id=session.id,
                    payload={"message": message},
                )
                return

            await self.repository.add_qa_message(paper.id, "user", request.message, [], session.id)

            async for event in self._run_ready_paper(request, paper, session, run.id):
                yield event
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            await self.repository.complete_agent_run(run.id, "failed", message)
            yield AgentChatEvent(
                event="error",
                run_id=run.id,
                session_id=session.id,
                payload={"message": message},
            )

    async def _run_ready_paper(
        self,
        request: AgentChatRequest,
        paper: PaperDetail,
        session: AgentSession,
        run_id: UUID,
    ) -> AsyncIterator[AgentChatEvent]:
        started = time.perf_counter()
        yield self._tool_event(run_id, session.id, "tool_started", "planner", "判断任务范围和推理深度")
        await self.repository.add_agent_run_step(
            run_id,
            "planner",
            "succeeded",
            f"scope={request.scope}, reasoning={request.reasoning_level}",
            elapsed_ms=_elapsed_ms(started),
        )
        yield self._tool_event(
            run_id,
            session.id,
            "tool_finished",
            "planner",
            "已限定为当前论文问答",
            {"scope": request.scope, "reasoning_level": request.reasoning_level},
        )

        retrieve_started = time.perf_counter()
        plan = self.retrieval.plan(request.message, request.reasoning_level, request.top_k)
        yield self._tool_event(
            run_id,
            session.id,
            "tool_started",
            "retrieve_passages",
            f"检索当前论文片段，top_k={plan.top_k}",
        )
        chunks = await self.retrieval.retrieve(
            paper.id,
            request.message,
            request.reasoning_level,
            request.top_k,
        )
        await self.repository.add_agent_run_step(
            run_id,
            "retrieve_passages",
            "succeeded",
            f"retrieved {len(chunks)} chunks",
            elapsed_ms=_elapsed_ms(retrieve_started),
            payload={"top_k": plan.top_k, "returned": len(chunks)},
        )
        yield self._tool_event(
            run_id,
            session.id,
            "tool_finished",
            "retrieve_passages",
            f"找到 {len(chunks)} 个候选证据片段",
            {"count": len(chunks)},
        )

        evidence_started = time.perf_counter()
        yield self._tool_event(run_id, session.id, "tool_started", "evidence_builder", "整理页码、坐标和片段")
        packet = self.evidence_builder.build(paper.id, request.message, chunks)
        citations = evidence_to_citations(packet)
        await self.repository.add_agent_run_step(
            run_id,
            "evidence_builder",
            "succeeded",
            f"built {len(packet.items)} evidence items",
            elapsed_ms=_elapsed_ms(evidence_started),
            payload={"evidence_count": len(packet.items)},
        )
        yield self._tool_event(
            run_id,
            session.id,
            "tool_finished",
            "evidence_builder",
            "证据包已生成",
            {"citations": [citation.model_dump(mode="json") for citation in citations]},
        )

        if not packet.items:
            answer = "无法从当前论文中找到足够证据回答这个问题。请换一种问法，或确认 PDF 已成功解析。"
            response = AskPaperResponse(
                answer=answer,
                citations=[],
                confidence=0.12,
                abstained=True,
                session_id=session.id,
                provider="local",
                model="evidence-fallback",
            )
            await self.repository.add_qa_message(paper.id, "assistant", answer, [], session.id)
            await self.repository.complete_agent_run(run_id, "succeeded")
            yield AgentChatEvent(
                event="final",
                run_id=run_id,
                session_id=session.id,
                payload=response.model_dump(mode="json"),
            )
            return

        model_started = time.perf_counter()
        selected_config = request.llm_config or self._env_openai_config()
        yield self._tool_event(run_id, session.id, "tool_started", "answer_with_citations", "基于证据调用回答模型")
        history = await self._history_summary(session.id)
        if selected_config:
            result = await answer_with_evidence(selected_config, paper, packet, history)
            answer = result.content
            provider = result.provider
            model = result.model
            usage = result.usage
            finish_reason = result.finish_reason
            confidence = min(0.92, 0.5 + (len(packet.items) * 0.05))
        else:
            answer = self._local_answer(packet)
            provider = "local"
            model = "evidence-fallback"
            usage = None
            finish_reason = None
            confidence = min(0.72, 0.38 + (len(packet.items) * 0.04))
        await self.repository.add_agent_run_step(
            run_id,
            "answer_with_citations",
            "succeeded",
            f"answered with {provider}/{model}",
            elapsed_ms=_elapsed_ms(model_started),
            payload={"provider": provider, "model": model},
        )
        yield self._tool_event(
            run_id,
            session.id,
            "tool_finished",
            "answer_with_citations",
            f"模型已生成回答：{provider}/{model}",
            {"provider": provider, "model": model},
        )

        verify_started = time.perf_counter()
        yield self._tool_event(run_id, session.id, "tool_started", "citation_verifier", "检查答案是否包含页码引用")
        verification = self.citation_verifier.verify(answer, packet, request.strict_citations)
        abstained = False
        if request.strict_citations and not verification.ok:
            answer = self._strict_fallback(packet, verification.detail)
            verification = self.citation_verifier.verify(answer, packet, request.strict_citations)
            abstained = verification.missing_citations
            confidence = min(confidence, 0.54)
        await self.repository.add_agent_run_step(
            run_id,
            "citation_verifier",
            "succeeded" if verification.ok else "failed",
            verification.detail,
            elapsed_ms=_elapsed_ms(verify_started),
            payload={"cited_pages": verification.cited_pages},
        )
        yield self._tool_event(
            run_id,
            session.id,
            "tool_finished",
            "citation_verifier",
            verification.detail,
            {"ok": verification.ok, "cited_pages": verification.cited_pages},
        )

        response = AskPaperResponse(
            answer=answer,
            citations=citations,
            confidence=confidence,
            abstained=abstained,
            session_id=session.id,
            provider=provider,
            model=model,
            usage=usage,
            finish_reason=finish_reason,
        )
        await self.repository.add_qa_message(
            paper.id,
            "assistant",
            answer,
            [citation.model_dump(mode="json") for citation in citations],
            session.id,
        )
        await self.repository.complete_agent_run(run_id, "succeeded")
        yield AgentChatEvent(
            event="final",
            run_id=run_id,
            session_id=session.id,
            payload=response.model_dump(mode="json"),
        )

    async def _session_for_request(self, request: AgentChatRequest) -> AgentSession:
        if request.session_id:
            session = await self.repository.get_qa_session(request.session_id)
            if session:
                return session
        title = _trim_title(request.message)
        return await self.repository.create_qa_session(request.paper_id, title)

    async def _history_summary(self, session_id: UUID) -> str:
        messages = await self.repository.list_qa_messages(session_id)
        recent = messages[-6:]
        return "\n".join(f"{message.role}: {_trim(message.content, 300)}" for message in recent)

    def _env_openai_config(self) -> LLMConfig | None:
        if not self.settings.openai_api_key:
            return None
        return LLMConfig(
            provider="openai",
            model=self.settings.openai_chat_model or "gpt-4.1-mini",
            api_key=self.settings.openai_api_key,
        )

    @staticmethod
    def _local_answer(packet) -> str:
        lines = ["基于当前论文中检索到的证据，可以先给出以下回答：", ""]
        for index, item in enumerate(packet.items[:4], start=1):
            lines.append(f"{index}. 第 {item.page_number} 页相关片段显示：{_trim(item.text, 420)} [p.{item.page_number}]")
        lines.extend(
            [
                "",
                "这是本地降级回答，只依据检索片段整理；配置 LLM 后可以生成更自然的综合答案。",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _strict_fallback(packet, reason: str) -> str:
        lines = [f"模型回答没有通过引用校验：{reason} 因此改为只返回可核验的证据摘要。", ""]
        for index, item in enumerate(packet.items[:4], start=1):
            lines.append(f"{index}. {_trim(item.text, 360)} [p.{item.page_number}]")
        return "\n".join(lines)

    @staticmethod
    def _tool_event(
        run_id: UUID,
        session_id: UUID,
        event: str,
        name: str,
        detail: str,
        payload: dict | None = None,
    ) -> AgentChatEvent:
        return AgentChatEvent(
            event=event,
            run_id=run_id,
            session_id=session_id,
            payload={"name": name, "detail": detail, **(payload or {})},
        )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _trim(text: str, max_chars: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def _trim_title(message: str) -> str:
    return _trim(message, 80)
