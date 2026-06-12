from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

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
from app.services.storage import normalize_doi, utcnow


class PostgresPaperRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def upsert_paper_from_result(self, result: PaperSearchResult) -> Paper:
        existing = await self._find_existing(result.doi, result.title)
        now = utcnow()
        if existing:
            merged_ids = _merge_source_ids(existing.source_ids, result.source_ids)
            async with await self._connect() as conn:
                row = await conn.execute(
                    """
                    UPDATE papers
                    SET title = %s,
                        authors = %s,
                        year = COALESCE(%s, year),
                        venue = COALESCE(%s, venue),
                        doi = COALESCE(%s, doi),
                        abstract = COALESCE(%s, abstract),
                        pdf_url = COALESCE(%s, pdf_url),
                        source_ids = %s,
                        updated_at = %s
                    WHERE id = %s
                    RETURNING *
                    """,
                    (
                        result.title or existing.title,
                        Jsonb(result.authors or existing.authors),
                        result.year,
                        result.venue,
                        result.doi,
                        result.abstract,
                        result.pdf_url,
                        Jsonb(merged_ids.model_dump()),
                        now,
                        existing.id,
                    ),
                )
                await conn.commit()
                return _paper_from_row(await row.fetchone())

        paper_id = uuid4()
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                INSERT INTO papers (
                  id, title, authors, abstract, year, venue, doi, pdf_url,
                  parse_status, source_ids, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'metadata_only', %s, %s, %s)
                RETURNING *
                """,
                (
                    paper_id,
                    result.title,
                    Jsonb(result.authors),
                    result.abstract,
                    result.year,
                    result.venue,
                    result.doi,
                    result.pdf_url,
                    Jsonb(result.source_ids.model_dump()),
                    now,
                    now,
                ),
            )
            await conn.commit()
            return _paper_from_row(await row.fetchone())

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
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                INSERT INTO papers (
                  id, title, authors, abstract, year, venue, doi, pdf_url,
                  parse_status, source_ids, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'metadata_only', %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    title,
                    Jsonb(authors),
                    abstract,
                    year,
                    venue,
                    doi,
                    pdf_url,
                    Jsonb(SourceIds(doi=doi).model_dump()),
                    now,
                    now,
                ),
            )
            await conn.commit()
            return _paper_from_row(await row.fetchone())

    async def get_paper(self, paper_id: UUID) -> PaperDetail | None:
        async with await self._connect() as conn:
            paper_cursor = await conn.execute("SELECT * FROM papers WHERE id = %s", (paper_id,))
            paper_row = await paper_cursor.fetchone()
            if not paper_row:
                return None

            asset_cursor = await conn.execute(
                "SELECT * FROM pdf_assets WHERE paper_id = %s ORDER BY created_at DESC LIMIT 1",
                (paper_id,),
            )
            asset_row = await asset_cursor.fetchone()

            pages_cursor = await conn.execute(
                "SELECT * FROM pdf_pages WHERE paper_id = %s ORDER BY page_number",
                (paper_id,),
            )
            page_rows = await pages_cursor.fetchall()

            chunks_cursor = await conn.execute(
                """
                SELECT COUNT(*) AS chunks_count,
                       COALESCE(jsonb_agg(DISTINCT section) FILTER (WHERE section IS NOT NULL), '[]'::jsonb) AS sections
                FROM text_chunks
                WHERE paper_id = %s
                """,
                (paper_id,),
            )
            chunk_summary = await chunks_cursor.fetchone()

        paper = _paper_from_row(paper_row)
        return PaperDetail(
            **paper.model_dump(),
            pdf_asset=_asset_from_row(asset_row) if asset_row else None,
            pages=[_page_from_row(row) for row in page_rows],
            chunks_count=chunk_summary["chunks_count"] or 0,
            sections=sorted(chunk_summary["sections"] or []),
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
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                INSERT INTO pdf_assets (id, paper_id, original_filename, storage_path, sha256, byte_size, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), paper_id, original_filename, storage_path, sha256, byte_size, now),
            )
            await conn.execute(
                """
                UPDATE papers
                SET pdf_path = %s, parse_status = 'queued', updated_at = %s
                WHERE id = %s
                """,
                (storage_path, now, paper_id),
            )
            await conn.commit()
            return _asset_from_row(await row.fetchone())

    async def replace_pages_and_chunks(
        self,
        paper_id: UUID,
        pages: list[PdfPage],
        chunks: list[TextChunk],
        embeddings: dict[UUID, list[float]],
    ) -> None:
        async with await self._connect() as conn:
            await conn.execute("DELETE FROM pdf_pages WHERE paper_id = %s", (paper_id,))
            await conn.execute("DELETE FROM text_chunks WHERE paper_id = %s", (paper_id,))

            for page in pages:
                await conn.execute(
                    """
                    INSERT INTO pdf_pages (id, paper_id, page_number, width, height, text, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        page.id,
                        page.paper_id,
                        page.page_number,
                        page.width,
                        page.height,
                        page.text,
                        page.created_at,
                    ),
                )

            for chunk in chunks:
                await conn.execute(
                    """
                    INSERT INTO text_chunks (
                      id, paper_id, page_number, section, bbox, text, token_count, embedding, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s)
                    """,
                    (
                        chunk.id,
                        chunk.paper_id,
                        chunk.page_number,
                        chunk.section,
                        Jsonb(chunk.bbox.model_dump() if chunk.bbox else None),
                        chunk.text,
                        chunk.token_count,
                        _vector_literal(embeddings[chunk.id]),
                        chunk.created_at,
                    ),
                )

            await conn.execute(
                "UPDATE papers SET parse_status = 'ready', updated_at = %s WHERE id = %s",
                (utcnow(), paper_id),
            )
            await conn.commit()

    async def set_parse_status(self, paper_id: UUID, status: str) -> None:
        async with await self._connect() as conn:
            await conn.execute(
                "UPDATE papers SET parse_status = %s, updated_at = %s WHERE id = %s",
                (status, utcnow(), paper_id),
            )
            await conn.commit()

    async def search_chunks(self, paper_id: UUID, query: str, limit: int) -> list[TextChunk]:
        from app.core.config import get_settings
        from app.services.embedding import stable_embedding

        settings = get_settings()
        query_embedding = stable_embedding(query, settings.embedding_dimensions)
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, paper_id, page_number, section, bbox, text, token_count, created_at,
                       ((0.72 * (1 - (embedding <=> %s::vector))) + (0.28 * similarity(text, %s))) AS score
                FROM text_chunks
                WHERE paper_id = %s
                ORDER BY score DESC
                LIMIT %s
                """,
                (_vector_literal(query_embedding), query, paper_id, limit),
            )
            rows = await cursor.fetchall()
        return [_chunk_from_row(row) for row in rows]

    async def get_chunk(self, paper_id: UUID, chunk_id: UUID) -> TextChunk | None:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, paper_id, page_number, section, bbox, text, token_count, created_at,
                       NULL::double precision AS score
                FROM text_chunks
                WHERE paper_id = %s AND id = %s
                LIMIT 1
                """,
                (paper_id, chunk_id),
            )
            row = await cursor.fetchone()
        return _chunk_from_row(row) if row else None

    async def add_qa_message(
        self,
        paper_id: UUID,
        role: str,
        content: str,
        citations: list[dict],
        session_id: UUID | None = None,
    ) -> UUID:
        message_id = uuid4()
        async with await self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO qa_messages (id, session_id, paper_id, role, content, citations, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (message_id, session_id, paper_id, role, content, Jsonb(citations), utcnow()),
            )
            await conn.commit()
        return message_id

    async def create_qa_session(self, paper_id: UUID, title: str | None = None) -> AgentSession:
        session_id = uuid4()
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                INSERT INTO qa_sessions (id, paper_id, title, created_at)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (session_id, paper_id, title, utcnow()),
            )
            await conn.commit()
            return _session_from_row(await row.fetchone())

    async def get_qa_session(self, session_id: UUID) -> AgentSession | None:
        async with await self._connect() as conn:
            cursor = await conn.execute("SELECT * FROM qa_sessions WHERE id = %s", (session_id,))
            row = await cursor.fetchone()
        return _session_from_row(row) if row else None

    async def list_qa_sessions(self, paper_id: UUID) -> list[AgentSession]:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM qa_sessions
                WHERE paper_id = %s
                ORDER BY created_at DESC
                """,
                (paper_id,),
            )
            rows = await cursor.fetchall()
        return [_session_from_row(row) for row in rows]

    async def list_qa_messages(self, session_id: UUID) -> list[AgentMessage]:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM qa_messages
                WHERE session_id = %s
                ORDER BY created_at
                """,
                (session_id,),
            )
            rows = await cursor.fetchall()
        return [_message_from_row(row) for row in rows]

    async def create_agent_run(
        self,
        session_id: UUID,
        paper_id: UUID,
        reasoning_level: str,
        strict_citations: bool,
    ) -> AgentRun:
        run_id = uuid4()
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                INSERT INTO agent_runs (
                  id, session_id, paper_id, status, reasoning_level,
                  strict_citations, created_at
                )
                VALUES (%s, %s, %s, 'running', %s, %s, %s)
                RETURNING *
                """,
                (run_id, session_id, paper_id, reasoning_level, strict_citations, utcnow()),
            )
            await conn.commit()
            return _run_from_row(await row.fetchone())

    async def complete_agent_run(
        self,
        run_id: UUID,
        status: str,
        error: str | None = None,
    ) -> None:
        async with await self._connect() as conn:
            await conn.execute(
                """
                UPDATE agent_runs
                SET status = %s, completed_at = %s, error = %s
                WHERE id = %s
                """,
                (status, utcnow(), error, run_id),
            )
            await conn.commit()

    async def add_agent_run_step(
        self,
        run_id: UUID,
        name: str,
        status: str,
        detail: str | None,
        elapsed_ms: int | None = None,
        payload: dict | None = None,
    ) -> AgentRunStep:
        async with await self._connect() as conn:
            row = await conn.execute(
                """
                INSERT INTO agent_run_steps (
                  id, run_id, name, status, detail, elapsed_ms, payload, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    run_id,
                    name,
                    status,
                    detail,
                    elapsed_ms,
                    Jsonb(payload or {}),
                    utcnow(),
                ),
            )
            await conn.commit()
            return _run_step_from_row(await row.fetchone())

    async def _find_existing(self, doi: str | None, title: str) -> Paper | None:
        normalized_doi = normalize_doi(doi)
        async with await self._connect() as conn:
            if normalized_doi:
                cursor = await conn.execute(
                    """
                    SELECT * FROM papers
                    WHERE lower(doi) = %s
                    LIMIT 1
                    """,
                    (normalized_doi,),
                )
                row = await cursor.fetchone()
                if row:
                    return _paper_from_row(row)
            cursor = await conn.execute(
                """
                SELECT * FROM papers
                WHERE lower(title) = lower(%s)
                LIMIT 1
                """,
                (title,),
            )
            row = await cursor.fetchone()
            return _paper_from_row(row) if row else None

    async def _connect(self):
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)


def _paper_from_row(row) -> Paper:
    return Paper(
        id=row["id"],
        title=row["title"],
        authors=list(row.get("authors") or []),
        year=row.get("year"),
        venue=row.get("venue"),
        doi=row.get("doi"),
        abstract=row.get("abstract"),
        pdf_url=row.get("pdf_url"),
        pdf_path=row.get("pdf_path"),
        parse_status=row.get("parse_status") or "metadata_only",
        source_ids=SourceIds(**(row.get("source_ids") or {})),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _asset_from_row(row) -> PdfAsset:
    return PdfAsset(
        id=row["id"],
        paper_id=row["paper_id"],
        original_filename=row.get("original_filename"),
        storage_path=row["storage_path"],
        sha256=row.get("sha256"),
        byte_size=row.get("byte_size"),
        created_at=row["created_at"],
    )


def _page_from_row(row) -> PdfPage:
    return PdfPage(
        id=row["id"],
        paper_id=row["paper_id"],
        page_number=row["page_number"],
        width=row["width"],
        height=row["height"],
        text=row["text"],
        created_at=row["created_at"],
    )


def _chunk_from_row(row) -> TextChunk:
    return TextChunk(
        id=row["id"],
        paper_id=row["paper_id"],
        page_number=row["page_number"],
        section=row.get("section"),
        bbox=BoundingBox(**row["bbox"]) if row.get("bbox") else None,
        text=row["text"],
        token_count=row["token_count"],
        score=float(row["score"]) if row.get("score") is not None else None,
        created_at=row["created_at"],
    )


def _session_from_row(row) -> AgentSession:
    return AgentSession(
        id=row["id"],
        paper_id=row["paper_id"],
        title=row.get("title"),
        created_at=row["created_at"],
    )


def _message_from_row(row) -> AgentMessage:
    return AgentMessage(
        id=row["id"],
        session_id=row.get("session_id"),
        paper_id=row["paper_id"],
        role=row["role"],
        content=row["content"],
        citations=row.get("citations") or [],
        created_at=row["created_at"],
    )


def _run_from_row(row) -> AgentRun:
    return AgentRun(
        id=row["id"],
        session_id=row["session_id"],
        paper_id=row["paper_id"],
        status=row.get("status") or "running",
        reasoning_level=row.get("reasoning_level") or "balanced",
        strict_citations=bool(row.get("strict_citations")),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
        error=row.get("error"),
    )


def _run_step_from_row(row) -> AgentRunStep:
    return AgentRunStep(
        id=row["id"],
        run_id=row["run_id"],
        name=row["name"],
        status=row.get("status") or "running",
        detail=row.get("detail"),
        elapsed_ms=row.get("elapsed_ms"),
        payload=row.get("payload") or {},
        created_at=row["created_at"],
    )


def _merge_source_ids(left: SourceIds, right: SourceIds) -> SourceIds:
    values = left.model_dump()
    for key, value in right.model_dump().items():
        if value and not values.get(key):
            values[key] = value
    return SourceIds(**values)


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
