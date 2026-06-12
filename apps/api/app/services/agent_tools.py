from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.models.schemas import AskPaperResponse, ImportPaperRequest, LLMConfig, PaperDetail, PaperSearchResult, TextChunk
from app.services.import_service import PaperImportService
from app.services.paper_sources import PaperSearchService, SourceFilter
from app.services.pdf_service import PdfService
from app.services.qa_agent import PaperQaAgent
from app.services.storage import PaperRepository


class PaperAgentTools:
    """Tool facade for orchestration layers that need stable paper-agent actions."""

    def __init__(
        self,
        repository: PaperRepository,
        search_service: PaperSearchService,
        import_service: PaperImportService,
        pdf_service: PdfService,
        qa_agent: PaperQaAgent,
    ) -> None:
        self.repository = repository
        self.search_service = search_service
        self.import_service = import_service
        self.pdf_service = pdf_service
        self.qa_agent = qa_agent

    async def search_papers(
        self,
        query: str,
        year_from: int | None = None,
        year_to: int | None = None,
        source: SourceFilter = "all",
        limit: int = 12,
    ) -> list[PaperSearchResult]:
        outcome = await self.search_service.search(query, year_from, year_to, source, limit)
        return outcome.results

    async def fetch_metadata(self, paper_id: UUID) -> PaperDetail | None:
        return await self.repository.get_paper(paper_id)

    async def download_or_upload_pdf(
        self,
        request: ImportPaperRequest | None = None,
        upload: UploadFile | None = None,
        existing_paper_id: UUID | None = None,
    ) -> PaperDetail:
        if request is not None:
            paper, _, _ = await self.import_service.import_paper(request)
            return paper
        if upload is None or existing_paper_id is None:
            raise ValueError("Provide either an import request or both upload and existing_paper_id.")
        paper = await self.repository.get_paper(existing_paper_id)
        if not paper:
            raise ValueError("Paper not found.")
        await self.pdf_service.save_upload(paper, upload)
        detail = await self.repository.get_paper(existing_paper_id)
        if not detail:
            raise ValueError("Paper not found after upload.")
        return detail

    async def parse_pdf(self, paper_id: UUID, pdf_path: str | Path) -> PaperDetail:
        await self.pdf_service.parse_and_index(paper_id, pdf_path)
        detail = await self.repository.get_paper(paper_id)
        if not detail:
            raise ValueError("Paper not found after parsing.")
        return detail

    async def retrieve_passages(self, paper_id: UUID, query: str, limit: int = 6) -> list[TextChunk]:
        return await self.repository.search_chunks(paper_id, query, limit)

    async def answer_with_citations(
        self,
        paper_id: UUID,
        question: str,
        top_k: int = 6,
        llm_config: LLMConfig | None = None,
    ) -> AskPaperResponse:
        return await self.qa_agent.answer(paper_id, question, top_k, llm_config)

    async def open_pdf_location(self, paper_id: UUID, chunk_id: UUID) -> dict:
        paper = await self.repository.get_paper(paper_id)
        if not paper:
            raise ValueError("Paper not found.")
        chunk = await self.repository.get_chunk(paper_id, chunk_id)
        if not chunk:
            raise ValueError("Chunk not found.")
        return {
            "paper_id": str(paper_id),
            "chunk_id": str(chunk_id),
            "page_number": chunk.page_number,
            "bbox": chunk.bbox.model_dump() if chunk.bbox else None,
            "pdf_path": paper.pdf_path,
        }
