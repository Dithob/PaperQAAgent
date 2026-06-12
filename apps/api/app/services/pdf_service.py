from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

import fitz
import httpx
from fastapi import UploadFile

from app.core.config import Settings
from app.models.schemas import BoundingBox, Paper
from app.services.embedding import stable_embedding
from app.services.storage import PaperRepository, make_chunk, make_page


class PdfService:
    def __init__(self, settings: Settings, repository: PaperRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.storage_path = settings.storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, paper: Paper, upload: UploadFile) -> Path:
        suffix = Path(upload.filename or "paper.pdf").suffix or ".pdf"
        target = self.storage_path / f"{paper.id}{suffix}"
        content = await upload.read()
        target.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        await self.repository.set_pdf_asset(
            paper.id,
            str(target),
            upload.filename,
            digest,
            len(content),
        )
        return target

    async def download_pdf(self, paper: Paper, pdf_url: str) -> Path:
        target = self.storage_path / f"{paper.id}.pdf"
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.request_timeout_seconds),
            follow_redirects=True,
        ) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not response.content.startswith(b"%PDF"):
                raise ValueError(f"URL did not return a PDF content type: {content_type}")
            target.write_bytes(response.content)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        await self.repository.set_pdf_asset(
            paper.id,
            str(target),
            Path(pdf_url).name or "downloaded.pdf",
            digest,
            target.stat().st_size,
        )
        return target

    async def parse_and_index(self, paper_id: UUID, pdf_path: str | Path) -> None:
        await self.repository.set_parse_status(paper_id, "parsing")
        pages = []
        chunks = []
        embeddings = {}
        try:
            document = fitz.open(str(pdf_path))
            for page_index, page in enumerate(document, start=1):
                page_text = page.get_text("text").strip()
                pages.append(
                    make_page(
                        paper_id=paper_id,
                        page_number=page_index,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        text=page_text,
                    )
                )
                page_chunks = self._chunks_for_page(paper_id, page_index, page)
                for chunk in page_chunks:
                    chunks.append(chunk)
                    embeddings[chunk.id] = stable_embedding(chunk.text, self.settings.embedding_dimensions)
            document.close()
            await self.repository.replace_pages_and_chunks(paper_id, pages, chunks, embeddings)
        except Exception:
            await self.repository.set_parse_status(paper_id, "failed")
            raise

    def _chunks_for_page(self, paper_id: UUID, page_number: int, page: fitz.Page):
        blocks = page.get_text("blocks")
        section = None
        pending_text: list[str] = []
        pending_bbox: BoundingBox | None = None

        for block in sorted(blocks, key=lambda item: (item[1], item[0])):
            if len(block) < 5:
                continue
            x0, y0, x1, y1, text = block[:5]
            clean = " ".join(str(text).split())
            if not clean:
                continue
            if _looks_like_section(clean):
                section = clean[:120]
            bbox = BoundingBox(
                x0=float(x0),
                y0=float(y0),
                x1=float(x1),
                y1=float(y1),
                page_width=float(page.rect.width),
                page_height=float(page.rect.height),
            )
            for part in _split_text(clean, target_words=120, max_words=220):
                if not pending_text:
                    pending_bbox = bbox
                pending_text.append(part)
                word_count = len(" ".join(pending_text).split())
                if word_count >= 120:
                    yield make_chunk(
                        paper_id=paper_id,
                        page_number=page_number,
                        section=section,
                        bbox=pending_bbox,
                        text=" ".join(pending_text),
                    )
                    pending_text = []
                    pending_bbox = None

        if pending_text:
            yield make_chunk(
                paper_id=paper_id,
                page_number=page_number,
                section=section,
                bbox=pending_bbox,
                text=" ".join(pending_text),
            )


def _split_text(text: str, target_words: int, max_words: int) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    parts = []
    for start in range(0, len(words), target_words):
        parts.append(" ".join(words[start : start + target_words]))
    return parts


def _looks_like_section(text: str) -> bool:
    if len(text) > 90:
        return False
    lowered = text.lower().strip()
    common = (
        "abstract",
        "introduction",
        "background",
        "related work",
        "method",
        "methods",
        "experiment",
        "experiments",
        "results",
        "discussion",
        "conclusion",
        "references",
    )
    if lowered in common:
        return True
    if lowered[:2].isdigit() and "." in lowered[:5]:
        return True
    return text.isupper() and len(text.split()) <= 8
