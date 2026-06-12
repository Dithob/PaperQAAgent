from app.core.config import Settings
from app.services.postgres_storage import PostgresPaperRepository
from app.services.storage import InMemoryPaperRepository, PaperRepository


_memory_repository: InMemoryPaperRepository | None = None
_postgres_repository: PostgresPaperRepository | None = None


def get_repository(settings: Settings) -> PaperRepository:
    global _memory_repository, _postgres_repository
    if settings.storage_backend == "postgres":
        if _postgres_repository is None:
            _postgres_repository = PostgresPaperRepository(settings.database_url)
        return _postgres_repository
    if _memory_repository is None:
        _memory_repository = InMemoryPaperRepository(settings.embedding_dimensions)
    return _memory_repository
