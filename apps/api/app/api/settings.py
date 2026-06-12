from fastapi import APIRouter

from app.models.schemas import LLMProviderTemplate
from app.services.llm_providers import provider_templates

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/llm/providers", response_model=list[LLMProviderTemplate])
async def get_llm_provider_templates() -> list[LLMProviderTemplate]:
    return provider_templates()
