"use client";

import { Download, FileSearch, Loader2, Search, Upload } from "lucide-react";
import { FormEvent, useRef, useState } from "react";
import { importPaper, searchPapers, uploadPaper } from "../lib/api";
import type { PaperDetail, PaperSearchResult, SourceStatus } from "../lib/types";

type Props = {
  selectedPaper: PaperDetail | null;
  onPaperSelected: (paper: PaperDetail) => void;
  onNotice: (message: string) => void;
};

export function SearchPanel({ selectedPaper, onPaperSelected, onNotice }: Props) {
  const [query, setQuery] = useState("retrieval augmented generation");
  const [source, setSource] = useState("all");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [hasPdf, setHasPdf] = useState(false);
  const [results, setResults] = useState<PaperSearchResult[]>([]);
  const [sourceStatuses, setSourceStatuses] = useState<SourceStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadTitle, setUploadTitle] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function submitSearch(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    try {
      const payload = await searchPapers({
        q: query,
        source,
        yearFrom,
        yearTo,
        hasPdf: hasPdf || undefined
      });
      setResults(payload.results);
      setSourceStatuses(payload.sources_status);
      onNotice(`Found ${payload.results.length} candidate papers.`);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleImport(result: PaperSearchResult) {
    setLoading(true);
    try {
      const paper = await importPaper(result);
      onPaperSelected(paper);
      onNotice(paper.parse_status === "ready" ? "Paper imported and parsed." : `Import status: ${paper.parse_status}`);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Import failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      onNotice("Choose a PDF first.");
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.set("file", file);
      if (uploadTitle) form.set("title", uploadTitle);
      form.set("parse_immediately", "true");
      const paper = await uploadPaper(form);
      onPaperSelected(paper);
      onNotice("Uploaded and parsed PDF.");
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <aside className="pane">
      <div className="pane-scroll">
        <div className="pane-inner">
          <p className="section-title">Search</p>
          <form onSubmit={submitSearch}>
            <div className="search-row">
              <input
                className="field"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Paper title, DOI, topic"
              />
              <button className="icon-button primary-button" title="Search papers" disabled={loading}>
                {loading ? <Loader2 size={18} /> : <Search size={18} />}
              </button>
            </div>
            <div className="control-grid">
              <select className="select" value={source} onChange={(event) => setSource(event.target.value)}>
                <option value="all">All sources</option>
                <option value="openalex">OpenAlex</option>
                <option value="semantic_scholar">Semantic Scholar</option>
                <option value="crossref">Crossref</option>
                <option value="arxiv">arXiv</option>
              </select>
              <input className="field" value={yearFrom} onChange={(event) => setYearFrom(event.target.value)} placeholder="From year" />
              <input className="field" value={yearTo} onChange={(event) => setYearTo(event.target.value)} placeholder="To year" />
            </div>
            <label className="check-row">
              <input type="checkbox" checked={hasPdf} onChange={(event) => setHasPdf(event.target.checked)} />
              <span>PDF only</span>
            </label>
          </form>

          {sourceStatuses.length ? (
            <div className="source-status-list">
              {sourceStatuses.map((status) => (
                <span className={`source-status ${status.ok ? "ok" : "failed"}`} key={status.source} title={status.error || undefined}>
                  {status.source}: {status.ok ? status.count : "failed"}
                </span>
              ))}
            </div>
          ) : null}

          <div className="result-list">
            {results.map((result, index) => (
              <article className="paper-card" key={`${result.title}-${index}`}>
                <div className="paper-title">{result.title}</div>
                <div className="paper-meta">
                  {[result.year, result.venue, (result.authors || []).slice(0, 3).join(", ")].filter(Boolean).join(" · ")}
                </div>
                {result.abstract ? <div className="small-muted">{trim(result.abstract, 220)}</div> : null}
                <div className="source-pills">
                  {(result.sources || []).map((item) => (
                    <span className="pill" key={item}>{item}</span>
                  ))}
                  {result.pdf_url ? <span className="pill">PDF</span> : null}
                  {result.citation_count ? <span className="pill">{result.citation_count} cites</span> : null}
                </div>
                <button className="secondary-button" onClick={() => handleImport(result)} disabled={loading}>
                  <Download size={16} />
                  Import
                </button>
              </article>
            ))}
          </div>

          <div className="upload-box">
            <p className="section-title">Upload PDF</p>
            <form className="qa-form" onSubmit={handleUpload}>
              <input className="field" value={uploadTitle} onChange={(event) => setUploadTitle(event.target.value)} placeholder="Optional paper title" />
              <input className="field" ref={fileRef} type="file" accept="application/pdf,.pdf" />
              <button className="primary-button" disabled={uploading}>
                {uploading ? <Loader2 size={16} /> : <Upload size={16} />}
                Upload
              </button>
            </form>
          </div>

          {selectedPaper ? (
            <div className="upload-box">
              <p className="section-title">Current Paper</p>
              <div className="paper-card">
                <div className="paper-title">{selectedPaper.title}</div>
                <div className="paper-meta">{selectedPaper.chunks_count || 0} chunks · {(selectedPaper.pages || []).length} pages</div>
                <span className={`status-badge ${selectedPaper.parse_status}`}>
                  <FileSearch size={14} /> {selectedPaper.parse_status}
                </span>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

function trim(text: string, max: number) {
  return text.length <= max ? text : `${text.slice(0, max - 3)}...`;
}
