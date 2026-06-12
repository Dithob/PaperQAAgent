from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from app.models.schemas import (
    AgentMessage,
    AgentRun,
    AgentRunStep,
    AgentSession,
    BoundingBox,
    Paper,
    PaperDetail,
    PaperSearchResult,
    PdfAsset,
    PdfPage,
    SourceIds,
    TextChunk,
)
from app.services.embedding import cosine_similarity, keyword_overlap, stable_embedding


def utcnow() -> datetime:
    return datetime.now(UTC)


class PaperRepository(Protocol):
    async def upsert_paper_from_result(self, result: PaperSearchResult) -> Paper: ...

    async def create_uploaded_paper(
        self,
        title: str,
        authors: list[str],
        year: int | None,
        venue: str | None,
        abstract: str | None,
        doi: str | None,
        pdf_url: str | None,
    ) -> Paper: ...

    async def get_paper(self, paper_id: UUID) -> PaperDetail | None: ...

    async def set_pdf_asset(
        self,
        paper_id: UUID,
        storage_path: str,
        original_filename: str | None,
        sha256: str | None,
        byte_size: int | None,
    ) -> PdfAsset: ...

    async def replace_pages_and_chunks(
        self,
        paper_id: UUID,
        pages: list[PdfPage],
        chunks: list[TextChunk],
        embeddings: dict[UUID, list[float]],
    ) -> None: ...

    async def set_parse_status(self, paper_id: UUID, status: str) -> None: ...

    async def search_chunks(self, paper_id: UUID, query: str, limit: int) -> list[TextChunk]: ...

    async def get_chunk(self, paper_id: UUID, chunk_id: UUID) -> TextChunk | None: ...

    async def add_qa_message(
        self,
        paper_id: UUID,
        role: str,
        content: str,
        citations: list[dict],
        session_id: UUID | None = None,
    ) -> UUID: ...

    async def create_qa_session(self, paper_id: UUID, title: str | None = None) -> AgentSession: ...

    async def get_qa_session(self, session_id: UUID) -> AgentSession | None: ...

    async def list_qa_sessions(self, paper_id: UUID) -> list[AgentSession]: ...

    async def list_qa_messages(self, session_id: UUID) -> list[AgentMessage]: ...

    async def create_agent_run(
        self,
        session_id: UUID,
        paper_id: UUID,
        reasoning_level: str,
        strict_citations: bool,
    ) -> AgentRun: ...

    async def complete_agent_run(
        self,
        run_id: UUID,
        status: str,
        error: str | None = None,
    ) -> None: ...

    async def add_agent_run_step(
        self,
        run_id: UUID,
        name: str,
        status: str,
        detail: str | None,
        elapsed_ms: int | None = None,
        payload: dict | None = None,
    ) -> AgentRunStep: ...


class InMemoryPaperRepository:
    def __init__(self, embedding_dimensions: int = 384) -> None:
        self.embedding_dimensions = embedding_dimensions
        self.papers: dict[UUID, Paper] = {}
        self.assets: dict[UUID, PdfAsset] = {}
        self.pages: dict[UUID, list[PdfPage]] = defaultdict(list)
        self.chunks: dict[UUID, list[TextChunk]] = defaultdict(list)
        self.embeddings: dict[UUID, list[float]] = {}
        self.qa_messages: list[dict] = []
        self.qa_sessions: dict[UUID, AgentSession] = {}
        self.agent_runs: dict[UUID, AgentRun] = {}
        self.agent_run_steps: list[AgentRunStep] = []

    async def upsert_paper_from_result(self, result: PaperSearchResult) -> Paper:
        existing = self._find_existing(result)
        now = utcnow()
        if existing:
            updated = existing.model_copy(
                update={
                    "title": result.title or existing.title,
                    "authors": result.authors or existing.authors,
                    "year": result.year or existing.year,
                    "venue": result.venue or existing.venue,
                    "doi": result.doi or existing.doi,
                    "abstract": result.abstract or existing.abstract,
                    "pdf_url": result.pdf_url or existing.pdf_url,
                    "source_ids": self._merge_source_ids(existing.source_ids, result.source_ids),
                    "updated_at": now,
                }
            )
            self.papers[updated.id] = updated
            return updated

        paper = Paper(
            id=uuid4(),
            title=result.title,
            authors=result.authors,
            year=result.year,
            venue=result.venue,
            doi=result.doi,
            abstract=result.abstract,
            pdf_url=result.pdf_url,
            pdf_path=None,
            parse_status="metadata_only",
            source_ids=result.source_ids,
            created_at=now,
            updated_at=now,
        )
        self.papers[paper.id] = paper
        return paper

    async def create_uploaded_paper(
        self,
        title: str,
        authors: list[str],
        year: int | None,
        venue: str | None,
        abstract: str | None,
        doi: str | None,
        pdf_url: str | None,
    ) -> Paper:
        now = utcnow()
        paper = Paper(
            id=uuid4(),
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            doi=doi,
            abstract=abstract,
            pdf_url=pdf_url,
            parse_status="metadata_only",
            source_ids=SourceIds(doi=doi),
            created_at=now,
            updated_at=now,
        )
        self.papers[paper.id] = paper
        return paper

    async def get_paper(self, paper_id: UUID) -> PaperDetail | None:
        paper = self.papers.get(paper_id)
        if not paper:
            return None
        chunks = self.chunks.get(paper_id, [])
        sections = sorted({chunk.section for chunk in chunks if chunk.section})
        return PaperDetail(
            **paper.model_dump(),
            pdf_asset=self.assets.get(paper_id),
            pages=self.pages.get(paper_id, []),
            chunks_count=len(chunks),
            sections=sections,
        )

    async def set_pdf_asset(
        self,
        paper_id: UUID,
        storage_path: str,
        original_filename: str | None,
        sha256: str | None,
        byte_size: int | None,
    ) -> PdfAsset:
        now = utcnow()
        asset = PdfAsset(
            id=uuid4(),
            paper_id=paper_id,
            original_filename=original_filename,
            storage_path=storage_path,
            sha256=sha256,
            byte_size=byte_size,
            created_at=now,
        )
        self.assets[paper_id] = asset
        paper = self.papers[paper_id]
        self.papers[paper_id] = paper.model_copy(
            update={"pdf_path": storage_path, "parse_status": "queued", "updated_at": now}
        )
        return asset

    async def replace_pages_and_chunks(
        self,
        paper_id: UUID,
        pages: list[PdfPage],
        chunks: list[TextChunk],
        embeddings: dict[UUID, list[float]],
    ) -> None:
        self.pages[paper_id] = pages
        self.chunks[paper_id] = chunks
        for chunk_id, embedding in embeddings.items():
            self.embeddings[chunk_id] = embedding
        await self.set_parse_status(paper_id, "ready")

    async def set_parse_status(self, paper_id: UUID, status: str) -> None:
        paper = self.papers[paper_id]
        self.papers[paper_id] = paper.model_copy(update={"parse_status": status, "updated_at": utcnow()})

    async def search_chunks(self, paper_id: UUID, query: str, limit: int) -> list[TextChunk]:
        query_embedding = stable_embedding(query, self.embedding_dimensions)
        scored: list[TextChunk] = []
        for chunk in self.chunks.get(paper_id, []):
            embedding = self.embeddings.get(chunk.id, [])
            vector_score = cosine_similarity(query_embedding, embedding)
            lexical_score = keyword_overlap(query, chunk.text)
            score = (0.72 * vector_score) + (0.28 * lexical_score)
            scored.append(chunk.model_copy(update={"score": round(score, 6)}))
        return sorted(scored, key=lambda item: item.score or 0, reverse=True)[:limit]

    async def get_chunk(self, paper_id: UUID, chunk_id: UUID) -> TextChunk | None:
        for chunk in self.chunks.get(paper_id, []):
            if chunk.id == chunk_id:
                return chunk
        return None

    async def add_qa_message(
        self,
        paper_id: UUID,
        role: str,
        content: str,
        citations: list[dict],
        session_id: UUID | None = None,
    ) -> UUID:
        message_id = uuid4()
        self.qa_messages.append(
            {
                "id": message_id,
                "paper_id": paper_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "citations": citations,
                "created_at": utcnow(),
            }
        )
        return message_id

    async def create_qa_session(self, paper_id: UUID, title: str | None = None) -> AgentSession:
        session = AgentSession(
            id=uuid4(),
            paper_id=paper_id,
            title=title,
            created_at=utcnow(),
        )
        self.qa_sessions[session.id] = session
        return session

    async def get_qa_session(self, session_id: UUID) -> AgentSession | None:
        return self.qa_sessions.get(session_id)

    async def list_qa_sessions(self, paper_id: UUID) -> list[AgentSession]:
        sessions = [session for session in self.qa_sessions.values() if session.paper_id == paper_id]
        return sorted(sessions, key=lambda session: session.created_at, reverse=True)

    async def list_qa_messages(self, session_id: UUID) -> list[AgentMessage]:
        messages = []
        for item in self.qa_messages:
            if item.get("session_id") != session_id:
                continue
            messages.append(
                AgentMessage(
                    id=item["id"],
                    session_id=item.get("session_id"),
                    paper_id=item["paper_id"],
                    role=item["role"],
                    content=item["content"],
                    citations=item.get("citations") or [],
                    created_at=item["created_at"],
                )
            )
        return sorted(messages, key=lambda message: message.created_at)

    async def create_agent_run(
        self,
        session_id: UUID,
        paper_id: UUID,
        reasoning_level: str,
        strict_citations: bool,
    ) -> AgentRun:
        run = AgentRun(
            id=uuid4(),
            session_id=session_id,
            paper_id=paper_id,
            status="running",
            reasoning_level=reasoning_level,
            strict_citations=strict_citations,
            created_at=utcnow(),
        )
        self.agent_runs[run.id] = run
        return run

    async def complete_agent_run(
        self,
        run_id: UUID,
        status: str,
        error: str | None = None,
    ) -> None:
        run = self.agent_runs.get(run_id)
        if not run:
            return
        self.agent_runs[run_id] = run.model_copy(
            update={"status": status, "completed_at": utcnow(), "error": error}
        )

    async def add_agent_run_step(
        self,
        run_id: UUID,
        name: str,
        status: str,
        detail: str | None,
        elapsed_ms: int | None = None,
        payload: dict | None = None,
    ) -> AgentRunStep:
        step = AgentRunStep(
            id=uuid4(),
            run_id=run_id,
            name=name,
            status=status,
            detail=detail,
            elapsed_ms=elapsed_ms,
            payload=payload or {},
            created_at=utcnow(),
        )
        self.agent_run_steps.append(step)
        return step

    def _find_existing(self, result: PaperSearchResult) -> Paper | None:
        doi = normalize_doi(result.doi)
        if doi:
            for paper in self.papers.values():
                if normalize_doi(paper.doi) == doi:
                    return paper
        title_key = normalize_title(result.title)
        for paper in self.papers.values():
            if normalize_title(paper.title) == title_key:
                return paper
        return None

    @staticmethod
    def _merge_source_ids(left: SourceIds, right: SourceIds) -> SourceIds:
        values = left.model_dump()
        for key, value in right.model_dump().items():
            if value and not values.get(key):
                values[key] = value
        return SourceIds(**values)


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    value = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    return value or None


def normalize_title(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", title.lower())
    return " ".join(normalized.split())


def make_page(paper_id: UUID, page_number: int, width: float, height: float, text: str) -> PdfPage:
    return PdfPage(
        id=uuid4(),
        paper_id=paper_id,
        page_number=page_number,
        width=width,
        height=height,
        text=text,
        created_at=utcnow(),
    )


def make_chunk(
    paper_id: UUID,
    page_number: int,
    section: str | None,
    bbox: BoundingBox | None,
    text: str,
) -> TextChunk:
    return TextChunk(
        id=uuid4(),
        paper_id=paper_id,
        page_number=page_number,
        section=section,
        bbox=bbox,
        text=text,
        token_count=max(1, len(text.split())),
        created_at=utcnow(),
    )
