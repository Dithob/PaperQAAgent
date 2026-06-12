from collections.abc import Generator

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.database import get_repository
from app.services.import_service import PaperImportService
from app.services.paper_sources import PaperSearchService
from app.services.paper_agent import PaperChatAgent
from app.services.pdf_service import PdfService
from app.services.qa_agent import PaperQaAgent
from app.services.storage import PaperRepository


def settings_dep() -> Settings:
    return get_settings()


def repository_dep(settings: Settings = Depends(settings_dep)) -> PaperRepository:
    return get_repository(settings)


def search_service_dep(settings: Settings = Depends(settings_dep)) -> PaperSearchService:
    return PaperSearchService(settings)


def pdf_service_dep(
    settings: Settings = Depends(settings_dep),
    repository: PaperRepository = Depends(repository_dep),
) -> PdfService:
    return PdfService(settings, repository)


def import_service_dep(
    settings: Settings = Depends(settings_dep),
    repository: PaperRepository = Depends(repository_dep),
    search_service: PaperSearchService = Depends(search_service_dep),
    pdf_service: PdfService = Depends(pdf_service_dep),
) -> PaperImportService:
    return PaperImportService(settings, repository, search_service, pdf_service)


def qa_agent_dep(
    settings: Settings = Depends(settings_dep),
    repository: PaperRepository = Depends(repository_dep),
) -> PaperQaAgent:
    return PaperQaAgent(settings, repository)


def paper_chat_agent_dep(
    settings: Settings = Depends(settings_dep),
    repository: PaperRepository = Depends(repository_dep),
) -> PaperChatAgent:
    return PaperChatAgent(settings, repository)


def lifespan_settings() -> Generator[Settings, None, None]:
    yield get_settings()
