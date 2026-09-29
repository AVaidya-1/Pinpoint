import { useEffect, useRef, type ReactNode } from 'react';
import type { Citation, DocInfo, Message } from './api';
import { Icon } from './icons';

export interface ActiveRef {
  messageId: string;
  n: number;
}

interface Props {
  doc: DocInfo | null;
  messages: Message[];
  busy: boolean;
  active: ActiveRef | null;
  onCite: (message: Message, c: Citation) => void;
  onClear: () => void;
  onClose: () => void;
}

const KIND: Record<Citation['kind'], string> = { text: 'Text', figure: 'Diagram', region: 'Region' };

/** Inline formatting: **bold** and [n] citation chips. */
function inline(text: string, msg: Message, props: Props, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|\[(\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] !== undefined) {
      out.push(<strong key={`${keyBase}-b${i++}`}>{m[1]}</strong>);
    } else {
      const n = Number(m[2]);
      const c = msg.citations.find((x) => x.n === n);
      const on = props.active?.messageId === msg.id && props.active.n === n;
      out.push(
        c ? (
          <button key={`${keyBase}-c${i++}`} className={`cite-chip${on ? ' is-on' : ''}`}
            title={`Page ${c.page} · ${KIND[c.kind]}`} onClick={() => props.onCite(msg, c)}>
            {n}
          </button>
        ) : null,
      );
    }
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** Paragraphs and "- " / "* " / "1. " lists. */
function Rich({ msg, props }: { msg: Message; props: Props }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const Tag = list.ordered ? 'ol' : 'ul';
    const k = blocks.length;
    blocks.push(<Tag key={`l${k}`}>{list.items.map((it, j) => <li key={j}>{inline(it, msg, props, `l${k}-${j}`)}</li>)}</Tag>);
    list = null;
  };
  msg.content.split('\n').forEach((raw) => {
    const line = raw.trim();
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const ordered = !!numbered;
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? numbered)![1]);
      return;
    }
    flush();
    if (line) blocks.push(<p key={`p${blocks.length}`}>{inline(line, msg, props, `p${blocks.length}`)}</p>);
  });
  flush();
  return <div className="rich">{blocks}</div>;
}

function modelName(model?: string) {
  if (!model) return '';
  const id = model.split(':').slice(1).join(':').split('/').pop() ?? model;
  return id.replace(/:free$/, '').replace('gemma-4-31b-it', 'Gemma 4 31B').replace('gemma-4-26b-a4b-it', 'Gemma 4 26B');
}

export function docStatus(doc: DocInfo): string | null {
  if (doc.status === 'indexing') return `Reading ${doc.indexed_pages} / ${doc.page_count} pages…`;
  if (doc.status === 'error') return doc.error ?? 'Could not read this PDF.';
  if (doc.visual_pages_total && doc.visual_pages_done < doc.visual_pages_total) {
    return `Ready to ask · indexing diagrams ${doc.visual_pages_done} / ${doc.visual_pages_total}…`;
  }
  if (doc.ocr_pages_total && doc.ocr_pages_done < doc.ocr_pages_total) {
    return `Ready to ask · reading scanned pages ${doc.ocr_pages_done} / ${doc.ocr_pages_total}…`;
  }
  return null;
}

export default function Chat(props: Props) {
  const { doc, messages, busy } = props;
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages.length, busy]);

  // Keep the selected answer in view when a citation is picked elsewhere.
  useEffect(() => {
    if (props.active) document.getElementById(`m-${props.active.messageId}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [props.active]);

  return (
    <aside className="chat">
      <header className="chat-head">
        <span className="chat-title">Answers</span>
        <span className="chat-count">{messages.filter((m) => m.role === 'assistant').length}</span>
        <div className="chat-head-actions">
          <button className="icon-btn" title="Clear answers" onClick={props.onClear} disabled={!messages.length || busy}>
            <Icon name="trash" />
          </button>
          <button className="icon-btn" title="Close panel (Ctrl+B)" onClick={props.onClose}>
            <Icon name="close" />
          </button>
        </div>
      </header>

      <div className="chat-list" ref={listRef}>
        {!messages.length && !busy && (
          <div className="chat-empty">
            <p>{doc ? 'Ask something in the search bar. Answers collect here; the highlight on the page is the source.' : 'Open a PDF to start.'}</p>
          </div>
        )}
        {messages.map((m) => m.role === 'user' ? (
          <div key={m.id} id={`m-${m.id}`} className="msg msg-user"><span className="msg-q">Q</span>{m.content}</div>
        ) : (
          <div key={m.id} id={`m-${m.id}`}
            className={`msg msg-ai${m.error ? ' is-error' : ''}${props.active?.messageId === m.id ? ' is-on' : ''}`}>
            {m.citations.length > 0 && (
              <div className="sources-row">
                {m.citations.map((c) => {
                  const on = props.active?.messageId === m.id && props.active.n === c.n;
                  return (
                    <button key={c.n} className={`source${on ? ' is-on' : ''}`} onClick={() => props.onCite(m, c)} title={c.snippet}>
                      <span className="source-n">{c.n}</span>
                      <span>p.{c.page}</span>
                      <span className="muted">{KIND[c.kind]}</span>
                    </button>
                  );
                })}
              </div>
            )}
            <Rich msg={m} props={props} />
            {m.meta?.model && (
              <div className="msg-meta">
                {modelName(m.meta.model)} · {m.meta.seconds}s · read {m.meta.pages_read?.length ?? 0}/{doc?.page_count ?? '?'} pages
                <button className="icon-btn icon-btn-sm" title="Copy answer"
                  onClick={() => navigator.clipboard?.writeText(m.content.replace(/\[\d+\]/g, ''))}>
                  <Icon name="copy" size={13} />
                </button>
              </div>
            )}
          </div>
        ))}
        {busy && <div className="msg msg-ai"><div className="thinking"><span className="dot" /><span className="dot" /><span className="dot" /></div></div>}
      </div>
      <div className="chat-foot">Answers can be wrong — check the highlighted source.</div>
    </aside>
  );
}
