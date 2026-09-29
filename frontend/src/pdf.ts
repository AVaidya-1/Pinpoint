// pdf.js setup. The viewer component module reads `globalThis.pdfjsLib`, so
// it must be imported only after the core library has been registered.
import * as pdfjsLib from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';

(globalThis as unknown as { pdfjsLib: typeof pdfjsLib }).pdfjsLib = pdfjsLib;
pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export { pdfjsLib };

export type ViewerLib = typeof import('pdfjs-dist/web/pdf_viewer.mjs');

let viewerLib: Promise<ViewerLib> | null = null;
export function loadViewerLib(): Promise<ViewerLib> {
  viewerLib ??= import('pdfjs-dist/web/pdf_viewer.mjs');
  return viewerLib;
}
