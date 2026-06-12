from app.models.schemas import PaperSearchResult
from app.services.storage import InMemoryPaperRepository, make_chunk


async def test_search_chunks_combines_vector_and_keyword_scores() -> None:
    repository = InMemoryPaperRepository(embedding_dimensions=128)
    paper = await repository.upsert_paper_from_result(PaperSearchResult(title="Graph RAG"))
    relevant = make_chunk(
        paper.id,
        2,
        "Method",
        None,
        "The method retrieves graph neighborhoods before generating grounded answers.",
    )
    distractor = make_chunk(
        paper.id,
        5,
        "Appendix",
        None,
        "The appendix lists unrelated hyperparameters for image augmentation.",
    )
    from app.services.embedding import stable_embedding

    await repository.replace_pages_and_chunks(
        paper.id,
        [],
        [distractor, relevant],
        {
            relevant.id: stable_embedding(relevant.text, 128),
            distractor.id: stable_embedding(distractor.text, 128),
        },
    )

    chunks = await repository.search_chunks(paper.id, "graph grounded retrieval", 2)

    assert chunks[0].id == relevant.id
    assert chunks[0].score is not None
