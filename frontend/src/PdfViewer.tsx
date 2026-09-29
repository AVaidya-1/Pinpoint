import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState, type ReactNode } from 'react';
import type { Box, Citation } from './api';
import { loadViewerLib, pdfjsLib } from './pdf';
import { Icon } from './icons';

type Viewer = InstanceType<Awaited<ReturnType<typeof loadViewerLib>>['PDFViewer']>;
type Bus = InstanceType<Awaited<ReturnType<typeof loadViewerLib>>['EventBus']>;
type Link = InstanceType<Awaited<ReturnType<typeof loadViewerLib>>['PDFLinkService']>;

export interface PdfViewerHandle {
  focus: (c: Citation) => void;
  zoomTo: (c: Citation) => void;
}

interface Props {
  source: string | null;
  filename?: string;
  citations: Citation[];
  active: Citation | null;
  showHighlights: boolean;
  /** Extra toolbar content before / after the viewer controls. */
  toolbarStart?: ReactNode;
  toolbarEnd?: ReactNode;
  onPages?: (pages: number) => void;
}

function union(boxes: Box[]): Box {
  return [
    Math.min(...boxes.map((b) => b[0])),
    Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])),
    Math.max(...boxes.map((b) => b[3])),
  ];
}

function place(el: HTMLElement, b: Box) {
  el.style.left = `${b[0] * 100}%`;
  el.style.top = `${b[1] * 100}%`;
  el.style.width = `${(b[2] - b[0]) * 100}%`;
  el.style.height = `${(b[3] - b[1]) * 100}%`;
}


/** "Fit width" never zooms past this, so wide panes don't blow pages up. */
const MAX_FIT_SCALE = 1;

function fitWidth(viewer: Viewer) {
  // A hidden or collapsed pane has no width to fit; wait for the next resize.
  if ((viewer.container?.clientWidth ?? 0) < 50) return;
  viewer.currentScaleValue = 'page-width';
  if (viewer.currentScale > MAX_FIT_SCALE) viewer.currentScale = MAX_FIT_SCALE;
}

const PdfViewer = forwardRef<PdfViewerHandle, Props>(function PdfViewer(props, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerDivRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const busRef = useRef<Bus | null>(null);
  const linkRef = useRef<Link | null>(null);
  const [ready, setReady] = useState(false);
  // True while the view should stay fitted to the width (until a manual zoom).
  const fitRef = useRef(true);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState('1');
  const [pages, setPages] = useState(0);
  const [scale, setScale] = useState(1);
  const [findOpen, setFindOpen] = useState(false);
  const [findQuery, setFindQuery] = useState('');
  const [findStatus, setFindStatus] = useState('');

  // Latest values for pdf.js event callbacks.
  const citesRef = useRef<Citation[]>([]);
  const activeRef = useRef<Citation | null>(null);
  const showRef = useRef(true);
  const onPagesRef = useRef(props.onPages);
  onPagesRef.current = props.onPages;
  citesRef.current = props.citations;
  activeRef.current = props.active;
  showRef.current = props.showHighlights;

  const paint = useCallback((pageNumber: number) => {
    const viewer = viewerRef.current;
    const pv = viewer?.getPageView(pageNumber - 1) as { div?: HTMLDivElement } | undefined;
    const div = pv?.div;
    if (!div) return;
    div.querySelector(':scope > .pp-hl-layer')?.remove();
    if (!showRef.current) return;
    const cites = citesRef.current.filter((c) => c.page === pageNumber && c.boxes.length);
    if (!cites.length) return;
    const layer = document.createElement('div');
    layer.className = 'pp-hl-layer';
    for (const c of cites) {
      const active = activeRef.current?.n === c.n;
      const group = document.createElement('div');
      group.className = `pp-hl-group kind-${c.kind}${active ? ' is-active' : ''}`;
      if (c.kind === 'figure' && c.precise && c.figure_box) {
        const ctx = document.createElement('div');
        ctx.className = 'pp-hl-context';
        place(ctx, c.figure_box);
        group.appendChild(ctx);
      }
      for (const b of c.boxes) {
        const el = document.createElement('div');
        el.className = 'pp-hl-box';
        place(el, b);
        group.appendChild(el);
      }
      const u = union(c.boxes);
      if (c.kind === 'text') {
        const bar = document.createElement('div');
        bar.className = 'pp-hl-bracket';
        place(bar, [Math.max(0, u[0] - 0.012), u[1], Math.max(0.004, u[0] - 0.006), u[3]]);
        group.appendChild(bar);
      }
      const badge = document.createElement('div');
      badge.className = 'pp-hl-badge';
      badge.textContent = String(c.n);
      badge.style.left = `${Math.max(0, (c.kind === 'text' ? u[0] - 0.012 : u[0]) * 100)}%`;
      badge.style.top = `${u[1] * 100}%`;
      group.appendChild(badge);
      layer.appendChild(group);
    }
    div.appendChild(layer);
  }, []);

  const repaintAll = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || !viewer.pagesCount) return;
    const pagesToPaint = new Set<number>(citesRef.current.map((c) => c.page));
    // Also clear stale layers on pages that no longer have citations.
    viewerDivRef.current?.querySelectorAll('.pp-hl-layer').forEach((el) => {
      const n = Number((el.parentElement as HTMLElement | null)?.dataset.pageNumber);
      if (n) pagesToPaint.add(n);
    });
    pagesToPaint.forEach((n) => n <= viewer.pagesCount && paint(n));
  }, [paint]);

  // Create the pdf.js viewer once.
  useEffect(() => {
    let cancelled = false;
    let wheel: ((e: WheelEvent) => void) | null = null;
    let resize: ResizeObserver | null = null;
    loadViewerLib().then((lib) => {
      if (cancelled || !containerRef.current || !viewerDivRef.current) return;
      const eventBus = new lib.EventBus();
      const linkService = new lib.PDFLinkService({ eventBus });
      const findController = new lib.PDFFindController({ eventBus, linkService });
      const viewer = new lib.PDFViewer({
        container: containerRef.current,
        viewer: viewerDivRef.current,
        eventBus,
        linkService,
        findController,
        textLayerMode: 1,
        removePageBorders: false,
      });
      linkService.setViewer(viewer);
      eventBus.on('pagesinit', () => {
        fitRef.current = true;
        fitWidth(viewer);
        setPages(viewer.pagesCount);
        onPagesRef.current?.(viewer.pagesCount);
      });
      eventBus.on('pagechanging', (e: { pageNumber: number }) => {
        setPage(e.pageNumber);
        setPageInput(String(e.pageNumber));
      });
      eventBus.on('scalechanging', (e: { scale: number }) => setScale(e.scale));
      eventBus.on('pagerendered', (e: { pageNumber: number }) => paint(e.pageNumber));
      eventBus.on('updatefindmatchescount', (e: { matchesCount: { current: number; total: number } }) => {
        const { current, total } = e.matchesCount;
        setFindStatus(total ? `${current} of ${total}` : 'No matches');
      });
      eventBus.on('updatefindcontrolstate', (e: { state: number; matchesCount?: { current: number; total: number } }) => {
        if (e.state === 1) setFindStatus('No matches');
        else if (e.matchesCount?.total) setFindStatus(`${e.matchesCount.current} of ${e.matchesCount.total}`);
      });
      viewerRef.current = viewer;
      busRef.current = eventBus;
      linkRef.current = linkService;
      wheel = (e: WheelEvent) => {
        if (!e.ctrlKey) return;
        e.preventDefault();
        fitRef.current = false;
        if (e.deltaY < 0) viewer.increaseScale();
        else viewer.decreaseScale();
      };
      containerRef.current.addEventListener('wheel', wheel, { passive: false });
      // Keep "fit width" fitted when the window or chat panel resizes.
      resize = new ResizeObserver(() => {
        if (viewer.pagesCount && fitRef.current) fitWidth(viewer);
        // Expose the scrollbar width so overlays can centre on the pages, not the pane.
        const c = viewer.container;
        c.closest<HTMLElement>('.viewer-pane')?.style.setProperty('--sbw', `${c.offsetWidth - c.clientWidth}px`);
      });
      resize.observe(containerRef.current);
      setReady(true);
    });
    const container = containerRef.current;
    return () => {
      cancelled = true;
      if (wheel && container) container.removeEventListener('wheel', wheel);
      resize?.disconnect();
    };
  }, [paint]);

  // Load the document whenever the source changes.
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!ready || !viewer) return;
    if (!props.source) {
      viewer.setDocument(null as never);
      setPages(0);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    const task = pdfjsLib.getDocument({ url: props.source });
    task.promise.then(
      (pdf) => {
        if (cancelled) return;
        viewer.setDocument(pdf);
        linkRef.current?.setDocument(pdf);
        setLoading(false);
      },
      (err) => {
        if (cancelled) return;
        setLoading(false);
        setLoadError(String(err?.message ?? err));
      },
    );
    return () => {
      cancelled = true;
      task.destroy();
    };
  }, [ready, props.source]);

  useEffect(() => {
    repaintAll();
  }, [props.citations, props.active, props.showHighlights, repaintAll]);

  const focus = useCallback((c: Citation) => {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    if (!viewer || !container || !viewer.pagesCount || !c.boxes.length) return;
    viewer.scrollPageIntoView({ pageNumber: c.page });
    requestAnimationFrame(() => {
      const pv = viewer.getPageView(c.page - 1) as { div?: HTMLDivElement } | undefined;
      const div = pv?.div;
      if (!div) return;
      const u = union(c.boxes);
      const boxH = (u[3] - u[1]) * div.clientHeight;
      // Centre small evidence; show large evidence from its top.
      const top = boxH < container.clientHeight * 0.6
        ? div.offsetTop + ((u[1] + u[3]) / 2) * div.clientHeight - container.clientHeight / 2
        : div.offsetTop + u[1] * div.clientHeight - 48;
      const wide = container.scrollWidth > container.clientWidth + 4;
      const left = wide
        ? div.offsetLeft + ((u[0] + u[2]) / 2) * div.clientWidth - container.clientWidth / 2
        : container.scrollLeft;
      container.scrollTo({ top: Math.max(0, top), left: Math.max(0, left), behavior: 'smooth' });
      paint(c.page);
    });
  }, [paint]);

  const zoomTo = useCallback((c: Citation) => {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    if (!viewer || !container || !viewer.pagesCount) return;
    const pv = viewer.getPageView(c.page - 1) as { viewport: { width: number } } | undefined;
    if (!pv) return;
    const u = union(c.figure_box && c.kind === 'figure' ? [c.figure_box] : c.boxes);
    const baseWidth = pv.viewport.width / viewer.currentScale;
    const target = (container.clientWidth * 0.85) / Math.max(0.05, (u[2] - u[0]) * baseWidth);
    fitRef.current = false;
    viewer.currentScale = Math.max(0.5, Math.min(4, target));
    setTimeout(() => focus(c), 60);
  }, [focus]);

  useImperativeHandle(ref, () => ({ focus, zoomTo }), [focus, zoomTo]);

  function goToPage(e: React.FormEvent) {
    e.preventDefault();
    const n = parseInt(pageInput, 10);
    const viewer = viewerRef.current;
    if (!viewer || Number.isNaN(n)) return;
    viewer.currentPageNumber = Math.min(Math.max(1, n), viewer.pagesCount);
  }

  function runFind(again = false, previous = false) {
    busRef.current?.dispatch('find', {
      source: null,
      type: again ? 'again' : '',
      query: findQuery,
      caseSensitive: false,
      entireWord: false,
      highlightAll: true,
      findPrevious: previous,
      matchDiacritics: false,
    });
  }

  const viewer = viewerRef.current;

  return (
    <div className="pv">
      <div className="pv-toolbar">
        <div className="pv-group pv-start">{props.toolbarStart}</div>
        <div className="pv-group">
          <button className="icon-btn" title="Zoom out (Ctrl + scroll)" onClick={() => { fitRef.current = false; viewer?.decreaseScale(); }} disabled={!pages}>
            <Icon name="minus" />
          </button>
          <span className="pv-scale">{Math.round(scale * 100)}%</span>
          <button className="icon-btn" title="Zoom in (Ctrl + scroll)" onClick={() => { fitRef.current = false; viewer?.increaseScale(); }} disabled={!pages}>
            <Icon name="plus" />
          </button>
          <button className="icon-btn" title="Fit width" onClick={() => { if (!viewer) return; fitRef.current = true; fitWidth(viewer); }} disabled={!pages}>
            <Icon name="fit" />
          </button>
          <button className={`icon-btn${findOpen ? ' is-on' : ''}`} title="Find text" onClick={() => setFindOpen((v) => !v)} disabled={!pages}>
            <Icon name="search" />
          </button>
        </div>
        <form className="pv-group" onSubmit={goToPage}>
          <button type="button" className="icon-btn" title="Previous page" onClick={() => viewer && (viewer.currentPageNumber = Math.max(1, page - 1))} disabled={!pages || page <= 1}>
            <Icon name="up" />
          </button>
          <input
            className="pv-page-input"
            value={pageInput}
            onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ''))}
            onBlur={() => setPageInput(String(page))}
            aria-label="Page number"
            disabled={!pages}
          />
          <span className="pv-muted">/ {pages || '–'}</span>
          <button type="button" className="icon-btn" title="Next page" onClick={() => viewer && (viewer.currentPageNumber = Math.min(pages, page + 1))} disabled={!pages || page >= pages}>
            <Icon name="down" />
          </button>
        </form>
        <div className="pv-group pv-end">{props.toolbarEnd}</div>
      </div>

      {findOpen && (
        <form className="pv-findbar" onSubmit={(e) => { e.preventDefault(); runFind(true); }}>
          <Icon name="search" />
          <input
            autoFocus
            placeholder="Find in document"
            value={findQuery}
            onChange={(e) => { setFindQuery(e.target.value); setFindStatus(''); }}
            onKeyDown={(e) => { if (e.key === 'Escape') setFindOpen(false); }}
          />
          <span className="pv-muted">{findStatus}</span>
          <button type="button" className="icon-btn" title="Previous match" onClick={() => runFind(true, true)}><Icon name="up" /></button>
          <button type="submit" className="icon-btn" title="Next match"><Icon name="down" /></button>
        </form>
      )}

      <div className="pv-stage">
        <div ref={containerRef} className="pv-container">
          <div ref={viewerDivRef} className="pdfViewer" />
        </div>
        {loading && <div className="pv-overlay-msg">Opening PDF…</div>}
        {loadError && <div className="pv-overlay-msg pv-error">Could not open this PDF: {loadError}</div>}
      </div>
    </div>
  );
});

export default PdfViewer;
