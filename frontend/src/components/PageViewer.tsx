import { useMemo, useState } from 'react';
import { TransformComponent, TransformWrapper, useControls } from 'react-zoom-pan-pinch';
import { pageImageUrl, type EvidenceBox } from '../api';
import type { Selection } from './DocumentList';

export type TestBox = [number, number, number, number];

export function readTestBox(): TestBox {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get('box');
  if (raw) {
    const parts = raw.split(',').map((s) => parseFloat(s));
    if (parts.length === 4 && parts.every((v) => Number.isFinite(v))) {
      const [x0, y0, x1, y1] = parts;
      if (x0 >= 0 && y0 >= 0 && x1 <= 1 && y1 <= 1 && x0 < x1 && y0 < y1) {
        return [x0, y0, x1, y1];
      }
    }
  }
  return [0.15, 0.22, 0.67, 0.48];
}

function isValidBox(b: EvidenceBox): boolean {
  return (
    Array.isArray(b) &&
    b.length === 4 &&
    b.every((v) => Number.isFinite(v)) &&
    b[0] >= 0 && b[1] >= 0 && b[2] <= 1 && b[3] <= 1 && b[0] < b[2] && b[1] < b[3]
  );
}

function ViewerControls() {
  const { resetTransform, setTransform } = useControls();
  return (
    <div className="ve-controls">
      <button data-testid="btn-fit" onClick={() => resetTransform()}>Fit</button>
      <button data-testid="btn-100" onClick={() => setTransform(0, 0, 1, 0)}>100%</button>
      <button data-testid="btn-200" onClick={() => setTransform(0, 0, 2, 0)}>200%</button>
      <button data-testid="btn-pan" onClick={() => setTransform(120, 80, 2, 0)}>Pan</button>
    </div>
  );
}

export default function PageViewer(props: { selection: Selection | null; boxes?: EvidenceBox[] }) {
  const [showHighlight, setShowHighlight] = useState(true);
  const fallback = useMemo(readTestBox, []);
  const boxes: EvidenceBox[] = useMemo(() => {
    const supplied = (props.boxes ?? []).filter(isValidBox);
    return supplied.length > 0 ? supplied : [fallback];
  }, [props.boxes, fallback]);

  if (!props.selection) {
    return <div className="ve-card" data-testid="page-viewer">No page selected.</div>;
  }

  return (
    <div className="ve-card" data-testid="page-viewer">
      <div>
        Page {props.selection.physicalPage}{' '}
        <button
          data-testid="btn-highlight"
          onClick={() => setShowHighlight((v) => !v)}
        >
          {showHighlight ? 'Hide highlight' : 'Show highlight'} (Toggle Highlight)
        </button>
      </div>
      <TransformWrapper initialScale={1} minScale={0.2} maxScale={8}>
        <ViewerControls />
        <TransformComponent>
          <div data-testid="page-stage" style={{ position: 'relative', display: 'inline-block', margin: 0, padding: 0 }}>
            <img
              data-testid="page-image"
              src={pageImageUrl(props.selection.pageId)}
              alt={`Page ${props.selection.physicalPage}`}
              style={{ display: 'block', margin: 0, padding: 0, border: 0 }}
            />
            {showHighlight && (
              <svg
                data-testid="page-overlay"
                viewBox="0 0 1000 1000"
                preserveAspectRatio="none"
                style={{ position: 'absolute', left: 0, top: 0, width: '100%', height: '100%', margin: 0, padding: 0, border: 0 }}
              >
                {boxes.map((b, i) => (
                  <rect
                    key={i}
                    data-testid={i === 0 ? 'highlight-rect' : `highlight-rect-${i}`}
                    x={b[0] * 1000}
                    y={b[1] * 1000}
                    width={(b[2] - b[0]) * 1000}
                    height={(b[3] - b[1]) * 1000}
                    fill="rgba(255, 220, 0, 0.25)"
                    stroke="red"
                    strokeWidth={4}
                  />
                ))}
              </svg>
            )}
          </div>
        </TransformComponent>
      </TransformWrapper>
    </div>
  );
}
