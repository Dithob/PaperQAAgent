from app.models.schemas import EvidencePacket, PaperSearchResult
from app.services.citation_verifier import CitationVerifier
from app.services.evidence_builder import EvidenceBuilder
from app.services.storage import InMemoryPaperRepository, make_chunk


async def test_evidence_builder_preserves_page_bbox_and_scores() -> None:
    repository = InMemoryPaperRepository(embedding_dimensions=128)
    paper = await repository.upsert_paper_from_result(PaperSearchResult(title="Agent Paper"))
    chunk = make_chunk(paper.id, 3, "Methods", None, "The agent retrieves evidence before answering.")
    chunk = chunk.model_copy(update={"score": 0.42})

    packet = EvidenceBuilder().build(paper.id, "How does it answer?", [chunk])

    assert packet.paper_id == paper.id
    assert packet.items[0].chunk_id == chunk.id
    assert packet.items[0].page_number == 3
    assert packet.items[0].score == 0.42


def test_citation_verifier_requires_page_citations_in_strict_mode() -> None:
    verifier = CitationVerifier()
    packet = EvidencePacket(
        paper_id="00000000-0000-0000-0000-000000000000",
        question="What is the method?",
        items=[
            {
                "chunk_id": "00000000-0000-0000-0000-000000000001",
                "page_number": 2,
                "text": "Method evidence",
            }
        ],
    )

    missing = verifier.verify("The method retrieves passages.", packet, strict=True)
    cited = verifier.verify("The method retrieves passages [p.2].", packet, strict=True)

    assert missing.ok is False
    assert missing.missing_citations is True
    assert cited.ok is True


async def test_agent_stream_emits_steps_and_final_for_ready_paper() -> None:
    from app.core.config import get_settings
    from app.models.schemas import AgentChatRequest
    from app.services.embedding import stable_embedding
    from app.services.paper_agent import PaperChatAgent

    repository = InMemoryPaperRepository(embedding_dimensions=128)
    paper = await repository.upsert_paper_from_result(PaperSearchResult(title="Grounded QA"))
    chunk = make_chunk(
        paper.id,
        1,
        "Method",
        None,
        "The system retrieves paper passages and answers only from evidence.",
    )
    await repository.replace_pages_and_chunks(
        paper.id,
        [],
        [chunk],
        {chunk.id: stable_embedding(chunk.text, 128)},
    )
    agent = PaperChatAgent(get_settings(), repository)

    events = [
        event async for event in agent.stream(
            AgentChatRequest(
                paper_id=paper.id,
                message="How does the system answer?",
                reasoning_level="fast",
                strict_citations=True,
            )
        )
    ]

    event_names = [event.event for event in events]
    assert "run_started" in event_names
    assert "tool_started" in event_names
    assert "tool_finished" in event_names
    assert event_names[-1] == "final"
    assert events[-1].payload["citations"]
    assert "[p.1]" in events[-1].payload["answer"]
