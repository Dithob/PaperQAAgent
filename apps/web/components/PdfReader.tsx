"use client";

import { ChevronLeft, ChevronRight, FileText, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { BoundingBox, PaperDetail } from "../lib/types";
import { pdfFileUrl } from "../lib/api";

type Props = {
  paper: PaperDetail | null;
  activeCitation?: { pageNumber: number; bbox?: BoundingBox | null } | null;
};

export function PdfReader({ paper, activeCitation }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [pdfDocument, setPdfDocument] = useState<any>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [scale, setScale] = useState(1.15);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const fileUrl = useMemo(() => pdfFileUrl(paper), [paper]);

  useEffect(() => {
    if (!fileUrl) {
      setPdfDocument(null);
      setPageCount(0);
      return;
    }
    let cancelled = false;
    import("pdfjs-dist").then((pdfjs) => {
      pdfjs.GlobalWorkerOptions.workerSrc = new URL(
        "pdfjs-dist/build/pdf.worker.min.js",
        import.meta.url
      ).toString();
      pdfjs.getDocument(fileUrl).promise.then((doc: any) => {
        if (!cancelled) {
          setPdfDocument(doc);
          setPageCount(doc.numPages);
          setPageNumber(1);
        }
      });
    });
    return () => {
      cancelled = true;
    };
  }, [fileUrl]);

  useEffect(() => {
    if (activeCitation?.pageNumber) {
      setPageNumber(activeCitation.pageNumber);
    }
  }, [activeCitation?.pageNumber]);

  useEffect(() => {
    if (!pdfDocument || !canvasRef.current) return;
    let cancelled = false;
    pdfDocument.getPage(pageNumber).then((page: any) => {
      if (cancelled) return;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas) return;
      const context = canvas.getContext("2d");
      if (!context) return;
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      setPageSize({ width: viewport.width, height: viewport.height });
      page.render({
        canvasContext: context,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0]
      });
    });
    return () => {
      cancelled = true;
    };
  }, [pdfDocument, pageNumber, scale]);

  const highlight = activeCitation?.bbox && activeCitation.pageNumber === pageNumber
    ? toHighlight(activeCitation.bbox, scale)
    : null;

  if (!paper) {
    return (
      <main className="pane">
        <div className="empty-state">
          <div>
            <h1>QAAgent</h1>
            <p>Search or upload a paper to start reading with cited answers.</p>
          </div>
        </div>
      </main>
    );
  }

  if (!fileUrl) {
    return (
      <main className="pane">
        <div className="empty-state">
          <div>
            <h1>{paper.title}</h1>
            <p>This paper has metadata but no PDF asset yet.</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="pane">
      <div className="viewer-shell">
        <div className="viewer-toolbar">
          <div className="viewer-title">{paper.title}</div>
          <div className="status-row">
            <button className="icon-button secondary-button" title="Previous page" onClick={() => setPageNumber(Math.max(1, pageNumber - 1))}>
              <ChevronLeft size={17} />
            </button>
            <span className="status-badge"><FileText size={14} /> {pageNumber} / {pageCount || "-"}</span>
            <button className="icon-button secondary-button" title="Next page" onClick={() => setPageNumber(Math.min(pageCount || 1, pageNumber + 1))}>
              <ChevronRight size={17} />
            </button>
            <button className="icon-button secondary-button" title="Zoom out" onClick={() => setScale(Math.max(0.7, scale - 0.1))}>
              <ZoomOut size={17} />
            </button>
            <button className="icon-button secondary-button" title="Zoom in" onClick={() => setScale(Math.min(2.2, scale + 0.1))}>
              <ZoomIn size={17} />
            </button>
          </div>
        </div>
        <div className="pdf-stage">
          <div className="pdf-page-wrap" style={{ width: pageSize.width || undefined, height: pageSize.height || undefined }}>
            <canvas ref={canvasRef} />
            {highlight ? <div className="highlight" style={highlight} /> : null}
          </div>
        </div>
      </div>
    </main>
  );
}

function toHighlight(bbox: BoundingBox, scale: number) {
  return {
    left: bbox.x0 * scale,
    top: bbox.y0 * scale,
    width: Math.max(8, (bbox.x1 - bbox.x0) * scale),
    height: Math.max(8, (bbox.y1 - bbox.y0) * scale)
  };
}
