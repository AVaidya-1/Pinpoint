import { useRef, useState } from 'react';
import { cancelJob, createSearch, getJob, getSearch, type SearchResult } from '../api';

export function outcomeWording(outcome: string, checked: number, total: number): string {
  switch (outcome) {
    case 'found':
      return `Found source regions. Checked ${checked} of ${total} pages.`;
    case 'no_evidence':
      return `I couldn't identify supporting evidence in these ${total} pages.`;
    case 'uncertain':
      return `I couldn't confidently locate a supporting region. Inspect the pages directly.`;
    case 'incomplete':
      return `Search incomplete: checked ${checked} of ${total} pages.`;
    case 'cancelled':
      return `Search cancelled: checked ${checked} of ${total} pages.`;
    default:
      return `Search ${outcome}: checked ${checked} of ${total} pages.`;
  }
}

export default function QuestionBar(props: {
  documentIds: string[];
  onResults: (r: SearchResult | null) => void;
}) {
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [outcome, setOutcome] = useState('');
  const [error, setError] = useState('');
  const cancelledRef = useRef(false);
  const activeJobRef = useRef<string | null>(null);

  async function poll(jobId: string, searchId: string) {
    // Search runs synchronously server-side; poll briefly for the record,
    // then fetch the final result. Keep polling while a job is active.
    for (let i = 0; i < 120; i++) {
      if (cancelledRef.current) break;
      const job = await getJob(jobId);
      const total = job.total_units || 0;
      const done = job.completed_units || 0;
      if (job.state === 'running' || job.state === 'queued') {
        setProgress(total > 0 ? `Checking page ${Math.min(done + 1, total)} of ${total}` : 'Checking pages…');
      } else {
        break;
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    if (cancelledRef.current) {
      setProgress('');
      setOutcome(`Search cancelled.`);
      setBusy(false);
      return;
    }
    const result = await getSearch(searchId);
    props.onResults(result);
    const { checked_pages, total_pages } = result.coverage;
    let wording = outcomeWording(result.outcome, checked_pages, total_pages);
    if (result.state === 'cancelled') {
      wording = `Search cancelled: checked ${checked_pages} of ${total_pages} pages.`;
    }
    if (result.errors.length > 0) {
      wording += ` Plus the specific failure state: ${result.errors.map((e) => e.code).join(', ')}`;
    }
    wording += ' Highlights are model-selected; inspect source.';
    setOutcome(wording);
    setProgress('');
    setBusy(false);
  }

  async function onFind() {
    if (busy) return;
    setError('');
    setOutcome('');
    props.onResults(null);
    const question = q.trim();
    if (!question) {
      setError('Type a question first.');
      return;
    }
    if (props.documentIds.length === 0) {
      setError('Select at least one document.');
      return;
    }
    setBusy(true);
    cancelledRef.current = false;
    try {
      const created = await createSearch(question, props.documentIds);
      activeJobRef.current = created.job_id;
      setProgress('Checking pages…');
      await poll(created.job_id, created.search_id);
    } catch (e: any) {
      const msg = e?.message ?? 'Search failed';
      if (/missing_key/i.test(msg)) {
        setError('Add a Gemini API key to the backend environment, then restart.');
      } else if (/quota/i.test(msg)) {
        setError('Model quota reached. Your documents and completed checks are saved.');
      } else {
        setError(msg);
      }
      setBusy(false);
      setProgress('');
    }
  }

  async function onCancel() {
    cancelledRef.current = true;
    if (activeJobRef.current) {
      try {
        await cancelJob(activeJobRef.current);
      } catch {
        /* job already finished; fall through */
      }
    }
  }

  return (
    <div className="ve-card" data-testid="question-bar">
      <input
        data-testid="question-input"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Ask a question about your documents..."
      />{' '}
      <button data-testid="ask-button" onClick={onFind} disabled={busy}>
        Find
      </button>{' '}
      {busy && (
        <button data-testid="cancel-button" onClick={onCancel}>
          Cancel
        </button>
      )}
      {progress && <div data-testid="search-progress">{progress}</div>}
      {outcome && <div data-testid="search-outcome">{outcome}</div>}
      {error && <div data-testid="search-error">{error}</div>}
      <div className="ve-note">Images are sent to Google for processing.</div>
    </div>
  );
}
