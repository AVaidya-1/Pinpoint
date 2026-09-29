import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from './api';
import type { Citation, DocInfo, Message } from './api';
import Chat, { docStatus, type ActiveRef } from './Chat';
import PdfViewer, { type PdfViewerHandle } from './PdfViewer';
import SearchDock, { type SearchDockHandle } from './SearchDock';
import { Icon } from './icons';

export default function App() {
  const [doc, setDoc] = useState<DocInfo | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [recent, setRecent] = useState<DocInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<ActiveRef | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [showHighlights, setShowHighlights] = useState(true);
  const [recentOpen, setRecentOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(() => {
    try { return localStorage.getItem('pp-panel') === '1'; } catch { return false; }
  });
  const viewerRef = useRef<PdfViewerHandle>(null);
  const dockRef = useRef<SearchDockHandle>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const docIdRef = useRef<string | null>(null);
  docIdRef.current = doc?.id ?? null;

  const refreshRecent = useCallback(() => {
    api.recentDocuments().then(setRecent).catch(() => {});
  }, []);

  const openDoc = useCallback(async (d: DocInfo) => {
    setDoc(d);
    setSource(api.fileUrl(d.id));
    setActive(null);
    setMessages([]);
    setUploadError(null);
    api.openDocument(d.id).then(refreshRecent).catch(() => {});
    try {
      const msgs = await api.getMessages(d.id);
      if (docIdRef.current === d.id) setMessages(msgs);
    } catch {
      /* chat history is optional */
    }
  }, [refreshRecent]);

  // Reopen the most recent PDF on start. If the server is unreachable, say
  // so and keep retrying until it comes up.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () => {
      api.recentDocuments().then((docs) => {
        setUploadError(null);
        setRecent(docs);
        if (docs.length && !docIdRef.current) openDoc(docs[0]);
      }).catch((e) => {
        setUploadError(e instanceof Error ? e.message : String(e));
        timer = setTimeout(load, 3000);
      });
    };
    load();
    return () => clearTimeout(timer);
  }, [openDoc]);

  // Poll while the PDF is being indexed or its scanned pages are OCR'd.
  const indexing = !!doc && !!doc.id && (doc.status === 'indexing'
    || (doc.status === 'ready' && (doc.ocr_pages_done < doc.ocr_pages_total
      || doc.visual_pages_done < doc.visual_pages_total || !doc.embedded)));
  useEffect(() => {
    if (!indexing || !doc) return;
    const id = doc.id;
    const t = setInterval(() => {
      api.getDocument(id).then((d) => { if (docIdRef.current === id) setDoc(d); }).catch(() => {});
    }, 1000);
    return () => clearInterval(t);
  }, [indexing, doc?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    try { localStorage.setItem('pp-panel', panelOpen ? '1' : '0'); } catch { /* ignore */ }
  }, [panelOpen]);

  // "/" focuses the search bar, Ctrl+B toggles the answer panel.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
      if (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        dockRef.current?.focus();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        setPanelOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  async function upload(file: File) {
    if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') {
      setUploadError('Please choose a PDF file.');
      return;
    }
    setUploadError(null);
    setActive(null);
    setMessages([]);
    // Show the PDF immediately from the local file while it uploads.
    const localUrl = URL.createObjectURL(file);
    setSource(localUrl);
    setDoc({
      id: '', filename: file.name, page_count: 0, status: 'indexing', indexed_pages: 0,
      ocr_pages_total: 0, ocr_pages_done: 0, embedded: false, visual_pages_total: 0,
      visual_pages_done: 0, error: null,
    });
    try {
      const d = await api.uploadPdf(file);
      setDoc(d);
      refreshRecent();
      const msgs = await api.getMessages(d.id);
      setMessages(msgs);
    } catch (e) {
      setDoc(null);
      setSource(null);
      setUploadError(e instanceof Error ? e.message : 'Upload failed.');
    }
  }

  const findCitation = useCallback((ref: ActiveRef | null): Citation | null => {
    if (!ref) return null;
    const m = messages.find((x) => x.id === ref.messageId);
    return m?.citations.find((c) => c.n === ref.n) ?? null;
  }, [messages]);

  function cite(m: Message, c: Citation) {
    setActive({ messageId: m.id, n: c.n });
    setShowHighlights(true);
    // Let the viewer receive the new citation set before focusing.
    requestAnimationFrame(() => viewerRef.current?.focus(c));
  }

  async function ask(question: string) {
    if (!doc?.id) return;
    const docId = doc.id;
    const temp: Message = {
      id: `tmp-${Date.now()}`, role: 'user', content: question, citations: [], meta: {}, created_at: Date.now() / 1000,
    };
    setMessages((ms) => [...ms, temp]);
    setActive(null);
    setBusy(true);
    try {
      const reply = await api.ask(docId, question);
      if (docIdRef.current !== docId) return;
      setMessages((ms) => [...ms, reply]);
      if (reply.citations.length) {
        const first = reply.citations[0];
        setShowHighlights(true);
        setActive({ messageId: reply.id, n: first.n });
        setTimeout(() => viewerRef.current?.focus(first), 50);
      }
    } catch (e) {
      const err: Message = {
        id: `err-${Date.now()}`, role: 'assistant', content: e instanceof Error ? e.message : 'Something went wrong.',
        citations: [], meta: {}, created_at: Date.now() / 1000, error: true,
      };
      setMessages((ms) => [...ms, err]);
    } finally {
      setBusy(false);
    }
  }

  async function clearChat() {
    if (!doc?.id) return;
    await api.clearMessages(doc.id).catch(() => {});
    setMessages([]);
    setActive(null);
  }

  // The answer whose highlights are on the page: the selected one, or the
  // latest answer when nothing is selected.
  const shownMessage = useMemo(() => {
    if (active) return messages.find((x) => x.id === active.messageId) ?? null;
    return [...messages].reverse().find((x) => x.role === 'assistant') ?? null;
  }, [messages, active]);
  const shownCitations = shownMessage?.citations ?? [];
  const shownQuestion = useMemo(() => {
    if (!shownMessage) return null;
    const i = messages.indexOf(shownMessage);
    for (let j = i - 1; j >= 0; j--) if (messages[j].role === 'user') return messages[j].content;
    return null;
  }, [messages, shownMessage]);

  const activeCitation = findCitation(active);
  const status = doc ? docStatus(doc) : null;
  const progress = doc?.status === 'indexing' && doc.page_count ? doc.indexed_pages / doc.page_count : null;

  const toolbarStart = (
    <>
      <button className={`icon-btn${panelOpen ? ' is-on' : ''}`} title="Answer panel (Ctrl+B)" onClick={() => setPanelOpen((v) => !v)}>
        <Icon name="panel" />
      </button>
      <span className="brand"><span className="brand-mark" />Pinpoint</span>
      {doc && (
        <span className="doc-name" title={doc.filename}>
          <span className="ellipsis">{doc.filename}</span>
          {status && <span className={`doc-status${doc.status === 'error' ? ' is-error' : ''}`}>{status}</span>}
        </span>
      )}
    </>
  );

  const toolbarEnd = (
    <>
      <div className="menu-wrap">
        <button className={`icon-btn${recentOpen ? ' is-on' : ''}`} title="Recent PDFs" onClick={() => setRecentOpen((v) => !v)} disabled={!recent.length}>
          <Icon name="clock" />
        </button>
        {recentOpen && (
          <div className="menu" onMouseLeave={() => setRecentOpen(false)}>
            <div className="menu-label">Recent</div>
            {recent.map((d) => (
              <button key={d.id} className={`menu-item${d.id === doc?.id ? ' is-on' : ''}`}
                onClick={() => { setRecentOpen(false); openDoc(d); }}>
                <Icon name="file" /> <span className="ellipsis">{d.filename}</span>
                <span className="menu-meta">{d.page_count}p</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <button className="btn" onClick={() => fileRef.current?.click()}><Icon name="upload" /> Open PDF</button>
    </>
  );

  return (
    <div
      className="app"
      onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDragging(true); } }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const f = e.dataTransfer.files?.[0];
        if (f) upload(f);
      }}
    >
      <input
        ref={fileRef}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload(f);
          e.target.value = '';
        }}
      />
      {panelOpen && (
        <Chat
          doc={doc}
          messages={messages}
          busy={busy}
          active={active}
          onCite={cite}
          onClear={clearChat}
          onClose={() => setPanelOpen(false)}
        />
      )}
      <main className="viewer-pane">
        {progress !== null && <div className="progress" style={{ width: `${Math.max(2, progress * 100)}%` }} />}
        <PdfViewer
          ref={viewerRef}
          source={source}
          filename={doc?.filename}
          citations={shownCitations}
          active={activeCitation}
          showHighlights={showHighlights}
          toolbarStart={toolbarStart}
          toolbarEnd={toolbarEnd}
        />
        {!source && (
          <button className="dropzone" onClick={() => fileRef.current?.click()}>
            <Icon name="upload" size={28} />
            <strong>Drop a PDF here or click to open</strong>
            <span className="muted">Ask a question and Pinpoint highlights the answer on the page — text, tables and diagrams.</span>
            {uploadError && <span className="error-text">{uploadError}</span>}
          </button>
        )}
        {source && uploadError && <div className="toast">{uploadError}</div>}
        <SearchDock
          ref={dockRef}
          doc={doc}
          busy={busy}
          answer={shownMessage}
          question={shownQuestion}
          active={activeCitation}
          showHighlights={showHighlights}
          panelOpen={panelOpen}
          onAsk={ask}
          onCite={cite}
          onToggleHighlights={() => setShowHighlights((v) => !v)}
          onZoom={() => activeCitation && viewerRef.current?.zoomTo(activeCitation)}
          onRecenter={() => activeCitation && viewerRef.current?.focus(activeCitation)}
          onOpenPanel={() => setPanelOpen(true)}
        />
      </main>
      {dragging && <div className="drag-veil"><Icon name="upload" size={32} /> Drop to open this PDF</div>}
    </div>
  );
}
