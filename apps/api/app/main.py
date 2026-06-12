from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.agent import router as agent_router
from app.api.llm import router as llm_router
from app.api.papers import router as papers_router
from app.api.settings import router as settings_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    app = FastAPI(
        title="QAAgent API",
        version="0.1.0",
        description="Paper search, PDF reading, and citation-grounded QA service.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(settings_router, prefix="/api")
    app.include_router(llm_router, prefix="/api")
    app.include_router(agent_router, prefix="/api")
    app.include_router(papers_router, prefix="/api")
    app.mount("/files/pdfs", StaticFiles(directory=str(settings.storage_path)), name="pdfs")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
