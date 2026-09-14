import { useCallback, useEffect, useState } from 'react';
import './App.css';
import { getHealth, listDocuments, type EvidenceBox, type SearchResult } from './api';
import DocumentList, { Selection } from './components/DocumentList';
import EvidenceList from './components/EvidenceList';
import PageViewer from './components/PageViewer';
import QuestionBar from './components/QuestionBar';

export default function App() {
  const [docs, setDocs] = useState<any[]>([]);
  const [capacity, setCapacity] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [viewerBoxes, setViewerBoxes] = useState<EvidenceBox[] | undefined>(undefined);

  const refresh = useCallback(async () => {
    const data = await listDocuments();
    setDocs(data.documents);
    setCapacity(data.capacity);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
    getHealth().then(setHealth).catch(() => {});
  }, [refresh]);

  const readyDocs = docs.filter((d: any) => d.status === 'ready');
  const documentIds = readyDocs.map((d: any) => d.id);

  function onSidebarSelect(sel: Selection) {
    setSelection(sel);
    setViewerBoxes(undefined);
  }

  function onEvidenceSelect(pageId: string, physicalPage: number, boxes: EvidenceBox[]) {
    const match = (result?.evidence ?? []).find((e) => e.page_id === pageId);
    setSelection({
      docId: match?.document_id ?? '',
      pageId,
      physicalPage,
    });
    setViewerBoxes(boxes);
  }

  return (
    <div>
      <header className="ve-header">
        <h1>Visual Evidence</h1>
        <span data-testid="capacity-header">
          {capacity ? `${capacity.total_pages} / ${capacity.max_pages} pages` : '…'}
        </span>
        <span data-testid="model-status">
          {health ? (health.key_present ? 'Model connected' : 'Model key missing') : '…'}
        </span>
      </header>
      <div className="ve-main">
        <div className="ve-side">
          <QuestionBar documentIds={documentIds} onResults={setResult} />
          <div className="ve-card" data-testid="search-scope">
            Searching {documentIds.length} document(s): {readyDocs.map((d: any) => d.filename).join(', ') || 'none yet'}
          </div>
          <DocumentList docs={docs} capacity={capacity} onChange={refresh} onSelect={onSidebarSelect} />
          <EvidenceList evidence={result?.evidence ?? []} onSelect={onEvidenceSelect} />
        </div>
        <div className="ve-viewer">
          <PageViewer selection={selection} boxes={viewerBoxes} />
        </div>
      </div>
    </div>
  );
}
