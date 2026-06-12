from __future__ import annotations

from uuid import UUID

from app.models.schemas import Citation, EvidenceItem, EvidencePacket, TextChunk


class EvidenceBuilder:
    def build(self, paper_id: UUID, question: str, chunks: list[TextChunk]) -> EvidencePacket:
        return EvidencePacket(
            paper_id=paper_id,
            question=question,
            items=[
                EvidenceItem(
                    chunk_id=chunk.id,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    bbox=chunk.bbox,
                    text=chunk.text,
                    score=chunk.score,
                )
                for chunk in chunks
            ],
        )


def evidence_to_citations(packet: EvidencePacket) -> list[Citation]:
    return [
        Citation(
            chunk_id=item.chunk_id,
            page_number=item.page_number,
            bbox=item.bbox,
            text=item.text,
            score=item.score,
        )
        for item in packet.items
    ]
