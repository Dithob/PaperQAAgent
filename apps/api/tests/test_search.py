from app.models.schemas import PaperSearchResult, SourceIds
from app.core.config import get_settings
from app.services.paper_sources import PaperSearchService, dedupe_results


def test_dedupe_merges_by_doi_and_preserves_pdf_url() -> None:
    left = PaperSearchResult(
        title="Attention Is All You Need",
        doi="10.48550/arXiv.1706.03762",
        citation_count=10,
        sources=["crossref"],
    )
    right = PaperSearchResult(
        title="Attention Is All You Need",
        doi="https://doi.org/10.48550/arXiv.1706.03762",
        pdf_url="https://arxiv.org/pdf/1706.03762",
        citation_count=20,
        source_ids=SourceIds(arxiv="1706.03762"),
        sources=["arxiv"],
    )

    results = dedupe_results([left, right])

    assert len(results) == 1
    assert results[0].pdf_url == "https://arxiv.org/pdf/1706.03762"
    assert results[0].citation_count == 20
    assert results[0].source_ids.arxiv == "1706.03762"


def test_dedupe_merges_by_near_identical_title() -> None:
    results = dedupe_results(
        [
            PaperSearchResult(title="Retrieval Augmented Generation for Knowledge Intensive NLP"),
            PaperSearchResult(title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"),
        ]
    )

    assert len(results) == 1


class WorkingAdapter:
    source = "openalex"

    async def search(self, client, params):
        return [PaperSearchResult(title="Working paper", pdf_url="https://example.test/paper.pdf", sources=["openalex"])]


class FailingAdapter:
    source = "crossref"

    async def search(self, client, params):
        raise RuntimeError("boom")


async def test_search_outcome_separates_source_errors() -> None:
    service = PaperSearchService(get_settings())
    service.adapters = {"openalex": WorkingAdapter(), "crossref": FailingAdapter()}

    outcome = await service.search("test", None, None, "all", 10)

    assert [result.title for result in outcome.results] == ["Working paper"]
    status = {item.source: item for item in outcome.sources_status}
    assert status["openalex"].ok is True
    assert status["crossref"].ok is False
    assert "boom" in (status["crossref"].error or "")


async def test_search_can_filter_pdf_results() -> None:
    service = PaperSearchService(get_settings())
    service.adapters = {"openalex": WorkingAdapter()}

    outcome = await service.search("test-pdf", None, None, "all", 10, has_pdf=True)

    assert len(outcome.results) == 1
    assert outcome.results[0].pdf_url
