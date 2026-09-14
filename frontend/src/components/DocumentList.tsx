import { useState } from 'react';
import { commitDocument, deleteDocument, listDocuments, parsePageRanges, uploadFile } from '../api';

export interface Selection {
  docId: string;
  pageId: string;
  physicalPage: number;
}

export default function DocumentList(props: {
  docs: any[];
  capacity: any;
  onChange: () => void;
  onSelect: (sel: Selection) => void;
}) {
  const [range, setRange] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError('');
    try {
      for (const file of Array.from(files)) {
        const up = await uploadFile(file);
        const pages = range.trim()
          ? parsePageRanges(range, up.page_count)
          : Array.from({ length: up.page_count }, (_, i) => i + 1);
        if (pages.length === 0) {
          setError(`No valid pages selected for ${file.name}`);
          continue;
        }
        await commitDocument(up.upload_id, pages);
      }
      await props.onChange();
    } catch (e: any) {
      setError(e.message ?? 'Upload failed');
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      await deleteDocument(id);
      await props.onChange();
    } catch (e: any) {
      setError(e.message ?? 'Delete failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ve-card" data-testid="document-list">
      <h3>Documents</h3>
      <div data-testid="capacity">
        {props.capacity ? `${props.capacity.total_pages}/${props.capacity.max_pages} pages` : '…'}
      </div>
      <div>
        <label>
          Page ranges (e.g. 1-4,7):{' '}
          <input
            data-testid="page-range"
            value={range}
            onChange={(e) => setRange(e.target.value)}
            placeholder="all pages"
          />
        </label>
      </div>
      <div>
        <label>
          Add documents:{' '}
          <input
            data-testid="file-input"
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg"
            disabled={busy}
            onChange={(e) => handleFiles(e.target.files)}
          />
        </label>
      </div>
      {error && <div data-testid="doc-error">{error}</div>}
      <ul>
        {props.docs.map((d: any) => (
          <li key={d.id} className="ve-doc" data-testid={`doc-${d.id}`}>
            <span>
              {d.filename} — pages {d.pages.map((p: any) => p.physical_page_number).join(',')}
            </span>{' '}
            <button data-testid={`delete-${d.id}`} onClick={() => remove(d.id)} disabled={busy}>
              Remove
            </button>
            <ul>
              {d.pages.map((p: any) => (
                <li key={p.id}>
                  <button
                    data-testid={`page-${d.id}-${p.physical_page_number}`}
                    onClick={() => props.onSelect({ docId: d.id, pageId: p.id, physicalPage: p.physical_page_number })}
                  >
                    Page {p.physical_page_number}
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}
