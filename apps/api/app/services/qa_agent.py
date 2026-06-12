from __future__ import annotations

from uuid import UUID

from app.core.config import Settings
from app.models.schemas import AskPaperResponse, Citation, LLMConfig, TextChunk
from app.services.llm_providers import answer_with_llm
from app.services.storage import PaperRepository


class PaperQaAgent:
    def __init__(self, settings: Settings, repository: PaperRepository) -> None:
        self.settings = settings
        self.repository = repository

    async def answer(
        self,
        paper_id: UUID,
        question: str,
        top_k: int,
        llm_config: LLMConfig | None = None,
    ) -> AskPaperResponse:
        chunks = await self.repository.search_chunks(paper_id, question, top_k)
        useful_chunks = [chunk for chunk in chunks if (chunk.score or 0) > 0.02]
        if not useful_chunks:
            answer = "无法从当前论文中找到足够证据回答这个问题。请换一种问法，或确认 PDF 已成功解析。"
            await self.repository.add_qa_message(paper_id, "user", question, [])
            await self.repository.add_qa_message(paper_id, "assistant", answer, [])
            return AskPaperResponse(
                answer=answer,
                citations=[],
                confidence=0.12,
                abstained=True,
                provider="local",
                model="evidence-fallback",
            )

        citations = [
            Citation(
                chunk_id=chunk.id,
                page_number=chunk.page_number,
                bbox=chunk.bbox,
                text=chunk.text,
                score=chunk.score,
            )
            for chunk in useful_chunks
        ]

        selected_config = llm_config or self._env_openai_config()
        provider = "local"
        model = "evidence-fallback"
        usage = None
        finish_reason = None
        if selected_config:
            result = await answer_with_llm(selected_config, question, useful_chunks)
            answer = result.content
            confidence = min(0.92, 0.48 + (len(useful_chunks) * 0.07))
            provider = result.provider
            model = result.model
            usage = result.usage
            finish_reason = result.finish_reason
        else:
            answer = self._local_answer(useful_chunks)
            confidence = min(0.72, 0.38 + (len(useful_chunks) * 0.05))

        await self.repository.add_qa_message(paper_id, "user", question, [])
        await self.repository.add_qa_message(
            paper_id,
            "assistant",
            answer,
            [citation.model_dump(mode="json") for citation in citations],
        )
        return AskPaperResponse(
            answer=answer,
            citations=citations,
            confidence=confidence,
            abstained=False,
            provider=provider,
            model=model,
            usage=usage,
            finish_reason=finish_reason,
        )

    def _env_openai_config(self) -> LLMConfig | None:
        if not self.settings.openai_api_key:
            return None
        return LLMConfig(
            provider="openai",
            model=self.settings.openai_chat_model or "gpt-4.1-mini",
            api_key=self.settings.openai_api_key,
        )

    @staticmethod
    def _local_answer(chunks: list[TextChunk]) -> str:
        lines = [
            "基于当前 PDF 中检索到的证据，可以给出以下回答：",
            "",
        ]
        for index, chunk in enumerate(chunks[:3], start=1):
            excerpt = _trim(chunk.text, 420)
            lines.append(f"{index}. 第 {chunk.page_number} 页的相关段落显示：{excerpt} [p.{chunk.page_number}]")
        lines.extend(
            [
                "",
                "这是本地降级回答，只依据检索片段整理；配置 LLM 后可生成更自然的综合答案。",
            ]
        )
        return "\n".join(lines)


def _trim(text: str, max_chars: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."
