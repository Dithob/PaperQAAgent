from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.api.deps import (
    import_service_dep,
    pdf_service_dep,
    qa_agent_dep,
    repository_dep,
    search_service_dep,
)
from app.models.schemas import (
    AskPaperRequest,
    AskPaperResponse,
    ImportPaperRequest,
    ImportPaperResponse,
    PaperDetail,
    SearchResponse,
    TextChunk,
)
from app.services.import_service import PaperImportService
from app.services.paper_sources import PaperSearchService, SourceFilter
from app.services.pdf_service import PdfService
from app.services.qa_agent import PaperQaAgent
from app.services.storage import PaperRepository

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("/search", response_model=SearchResponse)
async def search_papers(
    q: str = Query(min_length=2),
    year_from: int | None = None,
    year_to: int | None = None,
    source: SourceFilter = "all",
    has_pdf: bool | None = None,
    limit: int = Query(default=12, ge=1, le=50),
    service: PaperSearchService = Depends(search_service_dep),
) -> SearchResponse:
    outcome = await service.search(q, year_from, year_to, source, limit, has_pdf)
    return SearchResponse(query=q, results=outcome.results, sources_status=outcome.sources_status)


@router.post("/import", response_model=ImportPaperResponse)
async def import_paper(
    payload: ImportPaperRequest,
    service: PaperImportService = Depends(import_service_dep),
) -> ImportPaperResponse:
    paper, imported_pdf, message = await service.import_paper(payload)
    return ImportPaperResponse(paper=paper, imported_pdf=imported_pdf, message=message)


@router.post("/upload", response_model=ImportPaperResponse)
async def upload_paper(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    authors: str | None = Form(None),
    year: int | None = Form(None),
    venue: str | None = Form(None),
    abstract: str | None = Form(None),
    doi: str | None = Form(None),
    parse_immediately: bool = Form(True),
    repository: PaperRepository = Depends(repository_dep),
    pdf_service: PdfService = Depends(pdf_service_dep),
) -> ImportPaperResponse:
    if file.content_type and "pdf" not in file.content_type.lower():
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")
    paper = await repository.create_uploaded_paper(
        title=title or Path(file.filename or "Uploaded paper").stem,
        authors=[part.strip() for part in (authors or "").split(",") if part.strip()],
        year=year,
        venue=venue,
        abstract=abstract,
        doi=doi,
        pdf_url=None,
    )
    pdf_path = await pdf_service.save_upload(paper, file)
    if parse_immediately:
        await pdf_service.parse_and_index(paper.id, pdf_path)
    detail = await repository.get_paper(paper.id)
    return ImportPaperResponse(
        paper=detail or PaperDetail(**paper.model_dump()),
        imported_pdf=True,
        message="Uploaded and parsed PDF." if parse_immediately else "Uploaded PDF.",
    )


@router.get("/{paper_id}", response_model=PaperDetail)
async def get_paper(
    paper_id: UUID,
    repository: PaperRepository = Depends(repository_dep),
) -> PaperDetail:
    paper = await repository.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")
    return paper


@router.get("/{paper_id}/chunks", response_model=list[TextChunk])
async def get_chunks(
    paper_id: UUID,
    query: str = Query(default="", max_length=1000),
    limit: int = Query(default=10, ge=1, le=50),
    repository: PaperRepository = Depends(repository_dep),
) -> list[TextChunk]:
    paper = await repository.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")
    return await repository.search_chunks(paper_id, query or paper.title, limit)


@router.post("/{paper_id}/ask", response_model=AskPaperResponse)
async def ask_paper(
    paper_id: UUID,
    payload: AskPaperRequest,
    repository: PaperRepository = Depends(repository_dep),
    agent: PaperQaAgent = Depends(qa_agent_dep),
) -> AskPaperResponse:
    paper = await repository.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")
    if paper.parse_status != "ready":
        raise HTTPException(status_code=409, detail=f"Paper is not ready. Status: {paper.parse_status}")
    return await agent.answer(paper_id, payload.question, payload.top_k, payload.llm_config)
