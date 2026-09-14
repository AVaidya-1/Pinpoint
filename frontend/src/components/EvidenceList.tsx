import { pageImageUrl, type EvidenceBox, type EvidenceItem } from '../api';

const KIND_LABELS: Record<string, string> = {
  text: 'Text',
  table: 'Table',
  diagram: 'Diagram',
  chart: 'Chart',
  photo: 'Photo',
};

export default function EvidenceList(props: {
  evidence: EvidenceItem[];
  onSelect: (pageId: string, physicalPage: number, boxes: EvidenceBox[]) => void;
}) {
  if (!props.evidence || props.evidence.length === 0) {
    return (
      <div className="ve-card" data-testid="evidence-list">
        <h3>Results</h3>
        <div data-testid="evidence-empty">No search results yet. Ask a question to inspect the pages.</div>
      </div>
    );
  }
  return (
    <div className="ve-card" data-testid="evidence-list">
      <h3>Results</h3>
      <ul className="ve-evidence">
        {props.evidence.map((ev) => (
          <li key={ev.id} className="ve-evidence-card" data-testid={`evidence-card-${ev.id}`}>
            <button
              data-testid={`evidence-select-${ev.id}`}
              onClick={() => props.onSelect(ev.page_id, ev.physical_page_number, ev.boxes)}
              className="ve-evidence-button"
            >
              <img
                src={pageImageUrl(ev.page_id)}
                alt={`Source crop from ${ev.filename} page ${ev.physical_page_number}`}
                data-testid={`evidence-crop-${ev.id}`}
                className="ve-evidence-crop"
              />
              <span data-testid={`evidence-meta-${ev.id}`}>
                {ev.filename} · page {ev.physical_page_number} · {KIND_LABELS[ev.kind] ?? ev.kind}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
