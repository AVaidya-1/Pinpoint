export interface PageInfo {
  id: string;
  physical_page_number: number;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  mime_type: string;
  status: string;
  page_count: number;
  pages: PageInfo[];
  original_path: string;
}

export interface CapacityInfo {
  total_pages: number;
  max_pages: number;
  remaining: number;
  document_count: number;
  max_documents: number;
}

async function check(res: Response): Promise<any> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getHealth(): Promise<any> {
  const res = await fetch('/api/health');
  return check(res);
}

export async function listDocuments(): Promise<{ documents: DocumentInfo[]; capacity: CapacityInfo }> {
  const res = await fetch('/api/documents');
  return check(res);
}

export async function uploadFile(file: File): Promise<any> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/uploads', { method: 'POST', body: form });
  return check(res);
}

export async function commitDocument(upload_id: string, pages: number[]): Promise<any> {
  const res = await fetch('/api/documents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ upload_id, pages }),
  });
  return check(res);
}

export async function deleteDocument(id: string): Promise<any> {
  const res = await fetch(`/api/documents/${id}`, { method: 'DELETE' });
  return check(res);
}

export function pageImageUrl(pageId: string): string {
  return `/api/pages/${pageId}/image`;
}

export function parsePageRanges(spec: string, maxPage: number): number[] {
  const out = new Set<number>();
  for (const part of spec.split(',')) {
    const t = part.trim();
    if (!t) continue;
    const m = t.match(/^(\d+)\s*-\s*(\d+)$/);
    if (m) {
      let a = parseInt(m[1], 10);
      let b = parseInt(m[2], 10);
      if (a > b) [a, b] = [b, a];
      for (let p = a; p <= b; p++) {
        if (p >= 1 && p <= maxPage) out.add(p);
      }
    } else {
      const p = parseInt(t, 10);
      if (!Number.isNaN(p) && p >= 1 && p <= maxPage) out.add(p);
    }
  }
  return [...out].sort((a, b) => a - b);
}
