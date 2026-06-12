from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.deps import paper_chat_agent_dep, repository_dep
from app.models.schemas import AgentChatEvent, AgentChatRequest, AgentMessage, AgentSession
from app.services.paper_agent import PaperChatAgent
from app.services.storage import PaperRepository

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat/stream")
async def stream_agent_chat(
    payload: AgentChatRequest,
    agent: PaperChatAgent = Depends(paper_chat_agent_dep),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for event in agent.stream(payload):
            yield _sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/sessions", response_model=list[AgentSession])
async def list_agent_sessions(
    paper_id: UUID = Query(),
    repository: PaperRepository = Depends(repository_dep),
) -> list[AgentSession]:
    paper = await repository.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")
    return await repository.list_qa_sessions(paper_id)


@router.get("/sessions/{session_id}/messages", response_model=list[AgentMessage])
async def list_agent_messages(
    session_id: UUID,
    repository: PaperRepository = Depends(repository_dep),
) -> list[AgentMessage]:
    session = await repository.get_qa_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return await repository.list_qa_messages(session_id)


def _sse(event: AgentChatEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
