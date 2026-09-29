export interface DocInfo {
  id: string;
  filename: string;
  page_count: number;
  status: 'indexing' | 'ready' | 'error';
  indexed_pages: number;
  ocr_pages_total: number;
  ocr_pages_done: number;
  embedded: boolean;
  visual_pages_total: number;
  visual_pages_done: number;
  error: string | null;
}

/** Normalized [x0, y0, x1, y1] in 0-1 of the displayed page. */
export type Box = [number, number, number, number];

export interface Citation {
  n: number;
  page: number;
  kind: 'text' | 'figure' | 'region';
  boxes: Box[];
  figure_box?: Box;
  precise?: boolean;
  snippet: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  meta: { model?: string; pages_read?: number[]; seconds?: number };
  created_at: number;
  /** Client-only states. */
  pending?: boolean;
  error?: boolean;
}

export const OFFLINE_MESSAGE =
  "Can't reach the Pinpoint server. Start it with \"Start Pinpoint.cmd\" (it opens http://127.0.0.1:8000), then try again.";

/** fetch() that turns "server unreachable" into an actionable message. */
async function req(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch {
    throw new Error(OFFLINE_MESSAGE);
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const fileUrl = (id: string) => `/api/documents/${id}/file`;

export async function recentDocuments(): Promise<DocInfo[]> {
  return (await json<{ documents: DocInfo[] }>(await req('/api/documents'))).documents;
}

export async function uploadPdf(file: File): Promise<DocInfo> {
  const form = new FormData();
  form.append('file', file);
  return json<DocInfo>(await req('/api/documents', { method: 'POST', body: form }));
}

export async function getDocument(id: string): Promise<DocInfo> {
  return json<DocInfo>(await req(`/api/documents/${id}`));
}

export async function openDocument(id: string): Promise<DocInfo> {
  return json<DocInfo>(await req(`/api/documents/${id}/open`, { method: 'POST' }));
}

export async function getMessages(id: string): Promise<Message[]> {
  return (await json<{ messages: Message[] }>(await req(`/api/documents/${id}/messages`))).messages;
}

export async function clearMessages(id: string): Promise<void> {
  await json(await req(`/api/documents/${id}/messages`, { method: 'DELETE' }));
}

export async function ask(id: string, question: string): Promise<Message> {
  return json<Message>(
    await req(`/api/documents/${id}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }),
  );
}
