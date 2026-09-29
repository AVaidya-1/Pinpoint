import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import type { Citation, DocInfo, Message } from './api';
import { Icon } from './icons';
import { useLiquidGlass } from './glass';

export interface SearchDockHandle {
  focus: () => void;
}

interface Props {
  doc: DocInfo | null;
  busy: boolean;
  /** The answer whose highlights are on the page, and the question that produced it. */
  answer: Message | null;
  question: string | null;
  active: Citation | null;
  showHighlights: boolean;
  panelOpen: boolean;
  onAsk: (question: string) => void;
  onCite: (message: Message, c: Citation) => void;
  onToggleHighlights: () => void;
  onZoom: () => void;
  onRecenter: () => void;
  onOpenPanel: () => void;
}

const KIND: Record<Citation['kind'], string> = { text: 'Text', figure: 'Diagram', region: 'Region' };

/** One-line plain-text version of an answer. */
function summary(text: string) {
  return text.replace(/\[\d+\]/g, '').replace(/\*\*/g, '').replace(/^[-*•]\s+/gm, '').replace(/\s+/g, ' ').trim();
}

const SearchDock = forwardRef<SearchDockHandle, Props>(function SearchDock(props, ref) {
  const { doc, busy, answer, active } = props;
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // One glass surface for the whole dock (answer strip + input).
  const [glassRef, glassLayer, glassClass] = useLiquidGlass<HTMLDivElement>();

  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus() }), []);

  const ready = !!doc && doc.status === 'ready';
  const canAsk = ready && !busy;

  function submit() {
    const q = text.trim();
    if (!q || !canAsk) return;
    props.onAsk(q);
    setText('');
  }

  const cites = answer?.citations ?? [];
  const idx = active ? cites.findIndex((c) => c.n === active.n) : -1;
  const step = (d: number) => {
    if (!answer || !cites.length) return;
    const next = cites[(Math.max(idx, 0) + d + cites.length) % cites.length];
    props.onCite(answer, next);
  };

  const placeholder = !doc ? 'Open a PDF to start'
    : doc.status === 'indexing' ? `Reading the PDF… ${doc.indexed_pages} / ${doc.page_count} pages`
    : doc.status === 'error' ? 'This PDF could not be read'
    : 'Ask where something is in this PDF…';

  // Grow with the typed text only (an empty box is always one line).
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = '';
    if (text) el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [text]);

  return (
    <div ref={glassRef} className={`dock${glassClass}`}>
      {glassLayer}
      {(answer || busy) && (
        <div className={`dock-result${answer?.error ? ' is-error' : ''}`}>
          {busy ? (
            <div className="dock-row">
              <span className="dock-scan" />
              <span className="dock-status">Searching {doc?.page_count ?? ''} pages…</span>
            </div>
          ) : answer && (
            <>
              <div className="dock-row">
                {props.question && <span className="dock-q" title={props.question}>{props.question}</span>}
                {cites.length > 0 ? (
                  <div className="dock-cites">
                    {cites.map((c) => (
                      <button key={c.n} className={`dock-cite${active?.n === c.n ? ' is-on' : ''}`}
                        onClick={() => props.onCite(answer, c)} title={c.snippet}>
                        <span className="dock-cite-n">{c.n}</span>
                        p.{c.page}
                        <span className="dock-cite-kind">{KIND[c.kind]}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <span className="dock-status">{answer.error ? 'Error' : 'No location found'}</span>
                )}
                <div className="dock-tools">
                  {cites.length > 1 && (
                    <>
                      <button className="icon-btn" title="Previous source" onClick={() => step(-1)}><Icon name="left" /></button>
                      <button className="icon-btn" title="Next source" onClick={() => step(1)}><Icon name="right" /></button>
                    </>
                  )}
                  {cites.length > 0 && (
                    <>
                      <button className="icon-btn" title={props.showHighlights ? 'Hide highlights' : 'Show highlights'} onClick={props.onToggleHighlights}>
                        <Icon name={props.showHighlights ? 'eye' : 'eyeOff'} />
                      </button>
                      <button className="icon-btn" title="Zoom to highlight" onClick={props.onZoom} disabled={!active}><Icon name="zoomIn" /></button>
                      <button className="icon-btn" title="Re-center on highlight" onClick={props.onRecenter} disabled={!active}><Icon name="target" /></button>
                    </>
                  )}
                </div>
              </div>
              <button className="dock-answer" onClick={props.onOpenPanel} title="Open the answer panel (Ctrl+B)">
                <span className="ellipsis">{summary(answer.content)}</span>
                {!props.panelOpen && <span className="dock-more">Full answer <Icon name="panel" size={13} /></span>}
              </button>
            </>
          )}
        </div>
      )}

      <form className={`dock-bar${busy ? ' is-busy' : ''}`} onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <span className="dock-icon"><Icon name="search" size={18} /></span>
        <textarea
          ref={inputRef}
          rows={1}
          value={text}
          placeholder={placeholder}
          disabled={!ready}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            } else if (e.key === 'Escape') {
              inputRef.current?.blur();
            }
          }}
        />
        <kbd className="dock-kbd">/</kbd>
        <button type="submit" className="dock-go" disabled={!canAsk || !text.trim()} title="Find (Enter)">
          <Icon name="enter" />
        </button>
      </form>
    </div>
  );
});

export default SearchDock;
