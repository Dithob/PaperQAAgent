from __future__ import annotations

from app.core.config import Settings
from app.models.schemas import ImportPaperRequest, PaperDetail, PaperSearchResult, SourceIds
from app.services.paper_sources import PaperSearchService, SourceFilter
from app.services.pdf_service import PdfService
from app.services.storage import PaperRepository


class PaperImportService:
    def __init__(
        self,
        settings: Settings,
        repository: PaperRepository,
        search_service: PaperSearchService,
        pdf_service: PdfService,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.search_service = search_service
        self.pdf_service = pdf_service

    async def import_paper(self, request: ImportPaperRequest):
        metadata = await self._metadata_from_request(request)
        paper = await self.repository.upsert_paper_from_result(metadata)
        imported_pdf = False
        message = "Imported metadata."
        pdf_url = str(request.pdf_url or metadata.pdf_url or "")
        if pdf_url:
            try:
                pdf_path = await self.pdf_service.download_pdf(paper, pdf_url)
                imported_pdf = True
                message = "Imported metadata and PDF."
                if request.parse_immediately:
                    await self.pdf_service.parse_and_index(paper.id, pdf_path)
            except Exception as exc:
                await self.repository.set_parse_status(paper.id, "failed")
                message = f"Imported metadata, but PDF import failed: {type(exc).__name__}: {exc}"
        detail = await self.repository.get_paper(paper.id)
        return detail or PaperDetail(**paper.model_dump()), imported_pdf, message

    async def _metadata_from_request(self, request: ImportPaperRequest) -> PaperSearchResult:
        explicit_title = request.title or request.doi or request.arxiv_id or request.semantic_scholar_id
        source_ids = SourceIds(
            openalex=request.openalex_id,
            semantic_scholar=request.semantic_scholar_id,
            arxiv=request.arxiv_id,
            doi=request.doi,
        )
        if request.title:
            return PaperSearchResult(
                title=request.title,
                authors=request.authors,
                year=request.year,
                venue=request.venue,
                doi=request.doi,
                abstract=request.abstract,
                pdf_url=str(request.pdf_url) if request.pdf_url else None,
                source_ids=source_ids,
                sources=["pdf_url"] if request.pdf_url else [],
            )

        query = request.doi or request.arxiv_id or request.semantic_scholar_id or request.openalex_id
        if query:
            preferred_source: SourceFilter = "all"
            outcome = await self.search_service.search(query, None, None, preferred_source, 6)
            results = outcome.results
            real_results = [result for result in results if not result.title.endswith("search unavailable")]
            if real_results:
                best = real_results[0]
                return best.model_copy(
                    update={
                        "pdf_url": str(request.pdf_url) if request.pdf_url else best.pdf_url,
                        "source_ids": _merge_ids(best.source_ids, source_ids),
                    }
                )

        return PaperSearchResult(
            title=explicit_title or "Untitled paper",
            authors=request.authors,
            year=request.year,
            venue=request.venue,
            doi=request.doi,
            abstract=request.abstract,
            pdf_url=str(request.pdf_url) if request.pdf_url else None,
            source_ids=source_ids,
            sources=["pdf_url"] if request.pdf_url else [],
        )


def _merge_ids(left: SourceIds, right: SourceIds) -> SourceIds:
    values = left.model_dump()
    for key, value in right.model_dump().items():
        if value and not values.get(key):
            values[key] = value
    return SourceIds(**values)
