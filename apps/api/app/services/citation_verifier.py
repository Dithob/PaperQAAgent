from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.schemas import EvidencePacket


@dataclass(frozen=True)
class CitationVerification:
    ok: bool
    cited_pages: list[int]
    missing_citations: bool
    detail: str


class CitationVerifier:
    def verify(self, answer: str, packet: EvidencePacket, strict: bool) -> CitationVerification:
        cited_pages = sorted({int(match) for match in re.findall(r"\[p\.(\d+)\]", answer)})
        evidence_pages = {item.page_number for item in packet.items}
        has_any_citation = bool(cited_pages)
        all_pages_known = all(page in evidence_pages for page in cited_pages)
        ok = has_any_citation and all_pages_known
        if not strict and has_any_citation:
            ok = True
        if not packet.items:
            return CitationVerification(
                ok=False,
                cited_pages=[],
                missing_citations=True,
                detail="No evidence chunks were available.",
            )
        if ok:
            return CitationVerification(
                ok=True,
                cited_pages=cited_pages,
                missing_citations=False,
                detail="Answer includes page citations grounded in retrieved evidence.",
            )
        if not has_any_citation:
            detail = "Answer did not include page citations."
        else:
            detail = "Answer cited pages outside the retrieved evidence."
        return CitationVerification(
            ok=False,
            cited_pages=cited_pages,
            missing_citations=not has_any_citation,
            detail=detail,
        )
