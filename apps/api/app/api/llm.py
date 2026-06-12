from fastapi import APIRouter

from app.models.schemas import LLMConfig, LLMTestResponse
from app.services.llm_providers import test_llm_connection

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/test", response_model=LLMTestResponse)
async def test_llm(payload: LLMConfig) -> LLMTestResponse:
    return await test_llm_connection(payload)
