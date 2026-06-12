from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.schemas import ReasoningLevel, TextChunk
from app.services.storage import PaperRepository


@dataclass(frozen=True)
class RetrievalPlan:
    query: str
    top_k: int
    min_score: float


class RetrievalService:
    def __init__(self, repository: PaperRepository) -> None:
        self.repository = repository

    async def retrieve(
        self,
        paper_id: UUID,
        question: str,
        reasoning_level: ReasoningLevel,
        top_k: int | None = None,
    ) -> list[TextChunk]:
        plan = self.plan(question, reasoning_level, top_k)
        chunks = await self.repository.search_chunks(paper_id, plan.query, plan.top_k)
        return [chunk for chunk in chunks if (chunk.score or 0) >= plan.min_score]

    def plan(
        self,
        question: str,
        reasoning_level: ReasoningLevel,
        top_k: int | None = None,
    ) -> RetrievalPlan:
        default_top_k = {"fast": 5, "balanced": 8, "deep": 12}[reasoning_level]
        min_score = {"fast": 0.015, "balanced": 0.02, "deep": 0.02}[reasoning_level]
        query = self._query_for_level(question, reasoning_level)
        return RetrievalPlan(query=query, top_k=top_k or default_top_k, min_score=min_score)

    @staticmethod
    def _query_for_level(question: str, reasoning_level: ReasoningLevel) -> str:
        clean = " ".join(question.split())
        if reasoning_level == "fast":
            return clean
        if reasoning_level == "balanced":
            return f"{clean} method results evidence conclusion limitation"
        return (
            f"{clean} abstract introduction method methodology experiment results analysis "
            "ablation limitation conclusion evidence"
        )
