"use client";

import {
  Database,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Server,
  Settings,
} from "lucide-react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { useState } from "react";
import { AgentChat } from "../components/AgentChat";
import { PdfReader } from "../components/PdfReader";
import { SearchPanel } from "../components/SearchPanel";
import { SettingsPanel } from "../components/SettingsPanel";
import type { Citation, LLMConfig, PaperDetail } from "../lib/types";

export default function Home() {
  const [paper, setPaper] = useState<PaperDetail | null>(null);
  const [notice, setNotice] = useState("Ready");
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [llmConfig, setLlmConfig] = useState<LLMConfig | null>(null);
  const [libraryOpen, setLibraryOpen] = useState(true);
  const [libraryWidth, setLibraryWidth] = useState(320);
  const [readerOpen, setReaderOpen] = useState(true);
  const [readerWidth, setReaderWidth] = useState(520);
  const [resizingPane, setResizingPane] = useState<"library" | "reader" | null>(null);

  function selectPaper(nextPaper: PaperDetail) {
    setPaper(nextPaper);
    setActiveCitation(null);
  }

  function resizeLibrary(clientX: number) {
    const viewportWidth = window.innerWidth || 1440;
    const maxWidth = Math.min(520, Math.max(280, viewportWidth - (readerOpen ? readerWidth : 44) - 520));
    const nextWidth = Math.min(maxWidth, Math.max(260, clientX));
    setLibraryWidth(nextWidth);
  }

  function resizeReader(clientX: number) {
    const viewportWidth = window.innerWidth || 1440;
    const maxWidth = Math.min(920, Math.max(340, viewportWidth - (libraryOpen ? libraryWidth : 44) - 520));
    const nextWidth = Math.min(maxWidth, Math.max(320, viewportWidth - clientX));
    setReaderWidth(nextWidth);
  }

  function startLibraryResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (!libraryOpen) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setResizingPane("library");
    resizeLibrary(event.clientX);
  }

  function startReaderResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (!readerOpen) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setResizingPane("reader");
    resizeReader(event.clientX);
  }

  function movePaneResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (resizingPane === "library") resizeLibrary(event.clientX);
    if (resizingPane === "reader") resizeReader(event.clientX);
  }

  function stopPaneResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (!resizingPane) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setResizingPane(null);
  }

  const gridStyle = {
    "--library-width": `${libraryWidth}px`,
    "--reader-width": `${readerWidth}px`,
  } as CSSProperties;

  return (
    <div className={`workspace ${resizingPane ? "resizing" : ""}`}>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Database size={17} /></div>
          QAAgent
        </div>
        <div className="status-row">
          <button className="icon-button secondary-button" title="LLM settings" onClick={() => setSettingsOpen(true)}>
            <Settings size={16} />
          </button>
          <span className={`status-badge ${paper?.parse_status || ""}`}>
            <Server size={14} />
            {notice}
          </span>
        </div>
      </header>
      <div
        className={[
          "main-grid",
          libraryOpen ? "library-open" : "library-closed",
          readerOpen ? "reader-open" : "reader-closed",
        ].join(" ")}
        style={gridStyle}
      >
        <section className="library-pane-wrap" aria-hidden={!libraryOpen}>
          <SearchPanel selectedPaper={paper} onPaperSelected={selectPaper} onNotice={setNotice} />
        </section>
        <div
          className={`pane-resizer library-resizer ${libraryOpen ? "open" : "closed"}`}
          onPointerDown={startLibraryResize}
          onPointerMove={movePaneResize}
          onPointerUp={stopPaneResize}
          onPointerCancel={stopPaneResize}
          title={libraryOpen ? "Drag to resize paper library" : "Open paper library"}
        >
          <button
            className="icon-button secondary-button pane-toggle"
            title={libraryOpen ? "Hide paper library" : "Show paper library"}
            onClick={() => setLibraryOpen((current) => !current)}
            onPointerDown={(event) => event.stopPropagation()}
          >
            {libraryOpen ? <PanelLeftClose size={17} /> : <PanelLeftOpen size={17} />}
          </button>
        </div>
        <AgentChat
          paper={paper}
          llmConfig={llmConfig}
          activeCitationId={activeCitation?.chunk_id || null}
          onCitationSelected={setActiveCitation}
          onPaperSelected={selectPaper}
          onOpenSettings={() => setSettingsOpen(true)}
          onNotice={setNotice}
        />
        <div
          className={`pane-resizer reader-resizer ${readerOpen ? "open" : "closed"}`}
          onPointerDown={startReaderResize}
          onPointerMove={movePaneResize}
          onPointerUp={stopPaneResize}
          onPointerCancel={stopPaneResize}
          title={readerOpen ? "Drag to resize PDF reader" : "Open PDF reader"}
        >
          <button
            className="icon-button secondary-button pane-toggle"
            title={readerOpen ? "Hide PDF reader" : "Show PDF reader"}
            onClick={() => setReaderOpen((current) => !current)}
            onPointerDown={(event) => event.stopPropagation()}
          >
            {readerOpen ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}
          </button>
        </div>
        <section className="reader-pane-wrap" aria-hidden={!readerOpen}>
          <PdfReader
            paper={paper}
            activeCitation={
              activeCitation
                ? { pageNumber: activeCitation.page_number, bbox: activeCitation.bbox }
                : null
            }
          />
        </section>
      </div>
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onConfigChange={setLlmConfig}
        onNotice={setNotice}
      />
    </div>
  );
}
