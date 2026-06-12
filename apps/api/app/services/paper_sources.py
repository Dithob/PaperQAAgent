from __future__ import annotations

import html
import asyncio
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.models.schemas import PaperSearchResult, PaperSource, SourceIds, SourceStatus
from app.services.storage import normalize_doi, normalize_title


SourceFilter = Literal["all", "openalex", "semantic_scholar", "crossref", "arxiv"]


@dataclass(frozen=True)
class SearchParams:
    query: str
    year_from: int | None = None
    year_to: int | None = None
    limit: int = 12
    has_pdf: bool | None = None


@dataclass(frozen=True)
class SearchOutcome:
    results: list[PaperSearchResult]
    sources_status: list[SourceStatus]


_SEARCH_CACHE: dict[tuple, tuple[float, SearchOutcome]] = {}
_SEARCH_CACHE_TTL_SECONDS = 300


class PaperSourceAdapter:
    source: PaperSource

    async def search(self, client: httpx.AsyncClient, params: SearchParams) -> list[PaperSearchResult]:
        raise NotImplementedError


class OpenAlexAdapter(PaperSourceAdapter):
    source: PaperSource = "openalex"

    def __init__(self, mailto: str | None = None) -> None:
        self.mailto = mailto

    async def search(self, client: httpx.AsyncClient, params: SearchParams) -> list[PaperSearchResult]:
        filters = ["type:article|preprint"]
        if params.year_from:
            filters.append(f"from_publication_date:{params.year_from}-01-01")
        if params.year_to:
            filters.append(f"to_publication_date:{params.year_to}-12-31")
        query = {
            "search": params.query,
            "per-page": str(params.limit),
            "filter": ",".join(filters),
        }
        if self.mailto:
            query["mailto"] = self.mailto
        response = await client.get("https://api.openalex.org/works", params=query)
        response.raise_for_status()
        works = response.json().get("results", [])
        return [self._normalize(work) for work in works if work.get("display_name")]

    def _normalize(self, work: dict[str, Any]) -> PaperSearchResult:
        doi = normalize_doi(work.get("doi"))
        authors = [
            item.get("author", {}).get("display_name", "")
            for item in work.get("authorships", [])
            if item.get("author", {}).get("display_name")
        ]
        location = work.get("primary_location") or {}
        source = location.get("source") or {}
        pdf_url = (
            (location.get("pdf_url") or "")
            or (work.get("open_access") or {}).get("oa_url")
            or None
        )
        abstract = _openalex_abstract(work.get("abstract_inverted_index"))
        return PaperSearchResult(
            title=work["display_name"],
            authors=authors,
            year=work.get("publication_year"),
            venue=source.get("display_name"),
            doi=doi,
            abstract=abstract,
            pdf_url=pdf_url,
            citation_count=work.get("cited_by_count"),
            source_ids=SourceIds(openalex=work.get("id"), doi=doi),
            sources=["openalex"],
            url=work.get("id"),
            raw={"openalex": work},
        )


class SemanticScholarAdapter(PaperSourceAdapter):
    source: PaperSource = "semantic_scholar"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def search(self, client: httpx.AsyncClient, params: SearchParams) -> list[PaperSearchResult]:
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        fields = ",".join(
            [
                "paperId",
                "title",
                "authors",
                "year",
                "venue",
                "abstract",
                "url",
                "externalIds",
                "openAccessPdf",
                "citationCount",
                "referenceCount",
            ]
        )
        response = await client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": params.query, "limit": params.limit, "fields": fields},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        results = [self._normalize(item) for item in data if item.get("title")]
        return _filter_years(results, params.year_from, params.year_to)

    def _normalize(self, paper: dict[str, Any]) -> PaperSearchResult:
        external = paper.get("externalIds") or {}
        doi = normalize_doi(external.get("DOI"))
        arxiv_id = external.get("ArXiv")
        pdf = paper.get("openAccessPdf") or {}
        return PaperSearchResult(
            title=paper["title"],
            authors=[author.get("name", "") for author in paper.get("authors", []) if author.get("name")],
            year=paper.get("year"),
            venue=paper.get("venue"),
            doi=doi,
            abstract=paper.get("abstract"),
            pdf_url=pdf.get("url"),
            citation_count=paper.get("citationCount"),
            source_ids=SourceIds(
                semantic_scholar=paper.get("paperId"),
                arxiv=arxiv_id,
                doi=doi,
            ),
            sources=["semantic_scholar"],
            url=paper.get("url"),
            raw={"semantic_scholar": paper},
        )


class CrossrefAdapter(PaperSourceAdapter):
    source: PaperSource = "crossref"

    def __init__(self, mailto: str | None = None) -> None:
        self.mailto = mailto

    async def search(self, client: httpx.AsyncClient, params: SearchParams) -> list[PaperSearchResult]:
        query: dict[str, str | int] = {
            "query.bibliographic": params.query,
            "rows": params.limit,
            "select": "DOI,title,author,published-print,published-online,container-title,is-referenced-by-count,URL,abstract",
        }
        filters = []
        if params.year_from:
            filters.append(f"from-pub-date:{params.year_from}-01-01")
        if params.year_to:
            filters.append(f"until-pub-date:{params.year_to}-12-31")
        if filters:
            query["filter"] = ",".join(filters)
        headers = {"User-Agent": f"QAAgent/0.1 (mailto:{self.mailto})"} if self.mailto else {}
        response = await client.get("https://api.crossref.org/works", params=query, headers=headers)
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
        return [self._normalize(item) for item in items if item.get("title")]

    def _normalize(self, item: dict[str, Any]) -> PaperSearchResult:
        doi = normalize_doi(item.get("DOI"))
        year = _crossref_year(item)
        title = _first(item.get("title")) or "Untitled Crossref work"
        abstract = _strip_markup(item.get("abstract"))
        return PaperSearchResult(
            title=title,
            authors=[_crossref_author(author) for author in item.get("author", [])],
            year=year,
            venue=_first(item.get("container-title")),
            doi=doi,
            abstract=abstract,
            pdf_url=None,
            citation_count=item.get("is-referenced-by-count"),
            source_ids=SourceIds(crossref=doi, doi=doi),
            sources=["crossref"],
            url=item.get("URL"),
            raw={"crossref": item},
        )


class ArxivAdapter(PaperSourceAdapter):
    source: PaperSource = "arxiv"

    async def search(self, client: httpx.AsyncClient, params: SearchParams) -> list[PaperSearchResult]:
        response = await client.get(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{params.query}",
                "start": 0,
                "max_results": params.limit,
                "sortBy": "relevance",
                "sortOrder": "descending",
            },
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        results = [self._normalize(entry) for entry in entries]
        return _filter_years(results, params.year_from, params.year_to)

    def _normalize(self, entry: ET.Element) -> PaperSearchResult:
        atom = "{http://www.w3.org/2005/Atom}"
        arxiv = "{http://arxiv.org/schemas/atom}"
        title = _xml_text(entry.find(f"{atom}title")) or "Untitled arXiv paper"
        summary = _xml_text(entry.find(f"{atom}summary"))
        published = _xml_text(entry.find(f"{atom}published"))
        paper_url = _xml_text(entry.find(f"{atom}id"))
        arxiv_id = (paper_url or "").rstrip("/").split("/")[-1]
        doi = normalize_doi(_xml_text(entry.find(f"{arxiv}doi")))
        authors = [
            _xml_text(author.find(f"{atom}name")) or ""
            for author in entry.findall(f"{atom}author")
        ]
        pdf_url = None
        for link in entry.findall(f"{atom}link"):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href")
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{quote(arxiv_id)}"
        return PaperSearchResult(
            title=" ".join(title.split()),
            authors=[author for author in authors if author],
            year=int(published[:4]) if published and published[:4].isdigit() else None,
            venue="arXiv",
            doi=doi,
            abstract=" ".join(summary.split()) if summary else None,
            pdf_url=pdf_url,
            citation_count=None,
            source_ids=SourceIds(arxiv=arxiv_id, doi=doi),
            sources=["arxiv"],
            url=paper_url,
            raw={"arxiv_id": arxiv_id},
        )


class PaperSearchService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.adapters: dict[str, PaperSourceAdapter] = {
            "openalex": OpenAlexAdapter(settings.openalex_mailto),
            "semantic_scholar": SemanticScholarAdapter(settings.semantic_scholar_api_key),
            "crossref": CrossrefAdapter(settings.crossref_mailto),
            "arxiv": ArxivAdapter(),
        }

    async def search(
        self,
        query: str,
        year_from: int | None,
        year_to: int | None,
        source: SourceFilter,
        limit: int,
        has_pdf: bool | None = None,
    ) -> SearchOutcome:
        cache_key = (query.strip().lower(), year_from, year_to, source, limit, has_pdf)
        cached = _SEARCH_CACHE.get(cache_key)
        now = time.monotonic()
        if cached and now - cached[0] < _SEARCH_CACHE_TTL_SECONDS:
            return cached[1]

        params = SearchParams(
            query=query,
            year_from=year_from,
            year_to=year_to,
            limit=min(limit, self.settings.max_search_results_per_source),
            has_pdf=has_pdf,
        )
        selected = self.adapters.values() if source == "all" else [self.adapters[source]]
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            source_results: list[PaperSearchResult] = []
            sources_status: list[SourceStatus] = []
            for adapter in selected:
                start = time.perf_counter()
                results, error = await self._search_adapter_with_retry(client, adapter, params)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                source_results.extend(results)
                sources_status.append(
                    SourceStatus(
                        source=adapter.source,
                        ok=error is None,
                        count=len(results),
                        error=error,
                        elapsed_ms=elapsed_ms,
                    )
                )
            deduped = dedupe_results(_filter_pdf(source_results, has_pdf))[:limit]
            outcome = SearchOutcome(results=deduped, sources_status=sources_status)
            _SEARCH_CACHE[cache_key] = (now, outcome)
            return outcome

    async def _search_adapter_with_retry(
        self,
        client: httpx.AsyncClient,
        adapter: PaperSourceAdapter,
        params: SearchParams,
    ) -> tuple[list[PaperSearchResult], str | None]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return await adapter.search(client, params), None
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.25 * (attempt + 1))
        assert last_error is not None
        return [], f"{type(last_error).__name__}: {last_error}"


def dedupe_results(results: list[PaperSearchResult]) -> list[PaperSearchResult]:
    merged: list[PaperSearchResult] = []
    for result in results:
        duplicate_index = _find_duplicate_index(merged, result)
        if duplicate_index is None:
            merged.append(result)
            continue
        merged[duplicate_index] = _merge_results(merged[duplicate_index], result)
    return sorted(
        merged,
        key=lambda item: (
            item.citation_count is not None,
            item.citation_count or 0,
            item.year or 0,
        ),
        reverse=True,
    )


def _filter_pdf(results: list[PaperSearchResult], has_pdf: bool | None) -> list[PaperSearchResult]:
    if has_pdf is None:
        return results
    if has_pdf:
        return [result for result in results if result.pdf_url]
    return [result for result in results if not result.pdf_url]


def _find_duplicate_index(results: list[PaperSearchResult], candidate: PaperSearchResult) -> int | None:
    candidate_doi = normalize_doi(candidate.doi)
    candidate_arxiv = candidate.source_ids.arxiv
    for index, result in enumerate(results):
        if candidate_doi and normalize_doi(result.doi) == candidate_doi:
            return index
        if candidate_arxiv and result.source_ids.arxiv == candidate_arxiv:
            return index
        title_similarity = SequenceMatcher(
            None,
            normalize_title(result.title),
            normalize_title(candidate.title),
        ).ratio()
        if title_similarity >= 0.94:
            return index
    return None


def _merge_results(left: PaperSearchResult, right: PaperSearchResult) -> PaperSearchResult:
    left_sources = list(dict.fromkeys([*left.sources, *right.sources]))
    source_ids = SourceIds(
        **{
            key: left.source_ids.model_dump().get(key) or right.source_ids.model_dump().get(key)
            for key in SourceIds.model_fields
        }
    )
    raw = {**left.raw, **right.raw}
    return PaperSearchResult(
        title=left.title if len(left.title) >= len(right.title) else right.title,
        authors=left.authors or right.authors,
        year=left.year or right.year,
        venue=left.venue or right.venue,
        doi=left.doi or right.doi,
        abstract=left.abstract or right.abstract,
        pdf_url=left.pdf_url or right.pdf_url,
        citation_count=max(left.citation_count or 0, right.citation_count or 0) or None,
        source_ids=source_ids,
        sources=left_sources,
        url=left.url or right.url,
        raw=raw,
    )


def _openalex_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        words.extend((position, word) for position in positions)
    return " ".join(word for _, word in sorted(words))


def _filter_years(
    results: list[PaperSearchResult], year_from: int | None, year_to: int | None
) -> list[PaperSearchResult]:
    filtered = []
    for result in results:
        if year_from and result.year and result.year < year_from:
            continue
        if year_to and result.year and result.year > year_to:
            continue
        filtered.append(result)
    return filtered


def _first(value: list[str] | None) -> str | None:
    return value[0] if value else None


def _crossref_year(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "published"):
        date_parts = item.get(key, {}).get("date-parts")
        if date_parts and date_parts[0] and date_parts[0][0]:
            return int(date_parts[0][0])
    return None


def _crossref_author(author: dict[str, Any]) -> str:
    name = " ".join(part for part in [author.get("given"), author.get("family")] if part)
    return name or author.get("name") or ""


def _strip_markup(value: str | None) -> str | None:
    if not value:
        return None
    stripped = re.sub("<[^>]+>", " ", value)
    return " ".join(html.unescape(stripped).split())


def _xml_text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return element.text.strip()
