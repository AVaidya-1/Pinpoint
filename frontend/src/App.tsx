import { useCallback, useEffect, useState } from 'react';
import './App.css';
import { getHealth, listDocuments } from './api';
import DocumentList, { Selection } from './components/DocumentList';
import EvidenceList from './components/EvidenceList';
import PageViewer from './components/PageViewer';
import QuestionBar from './components/QuestionBar';

export default function App() {
  const [docs, setDocs] = useState<any[]>([]);
  const [capacity, setCapacity] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [selection, setSelection] = useState<Selection | null>(null);

  const refresh = useCallback(async () => {
    const data = await listDocuments();
    setDocs(data.documents);
    setCapacity(data.capacity);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
    getHealth().then(setHealth).catch(() => {});
  }, [refresh]);

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
          <QuestionBar />
          <DocumentList docs={docs} capacity={capacity} onChange={refresh} onSelect={setSelection} />
          <EvidenceList />
        </div>
        <div className="ve-viewer">
          <PageViewer selection={selection} />
        </div>
      </div>
    </div>
  );
}
