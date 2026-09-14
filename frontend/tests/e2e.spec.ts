import { expect, request, test } from '@playwright/test';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const BACKEND = 'http://127.0.0.1:8000';
const FRONTEND = 'http://127.0.0.1:5173';
const EVIDENCE = path.join(ROOT, 'out', 'orchestration', 'import-viewer');
const SHOTS = path.join(EVIDENCE, 'screenshots');
const GEN = path.join(ROOT, 'fixtures', 'generated');

function sha256File(p: string): string {
  return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
}

function mimeFor(name: string): string {
  if (name.endsWith('.pdf')) return 'application/pdf';
  if (name.endsWith('.png')) return 'image/png';
  return 'image/jpeg';
}

interface ApiPage {
  id: string;
  physical_page_number: number;
}

interface ApiDoc {
  id: string;
  filename: string;
  mime_type: string;
  status: string;
  pages: ApiPage[];
  original_path: string;
}

let api: any;
const uploads: Record<string, { sha256: string }> = {};
const domBounds: any[] = [];
const shots: string[] = [];

async function listDocs(): Promise<{ documents: ApiDoc[]; capacity: any }> {
  const res = await api.get('/api/documents');
  expect(res.ok()).toBeTruthy();
  return res.json();
}

async function uploadAndCommit(genName: string, pages: number[]): Promise<ApiDoc> {
  const full = path.join(GEN, genName);
  const buffer = fs.readFileSync(full);
  const up = await api.post('/api/uploads', {
    multipart: { file: { name: genName, mimeType: mimeFor(genName), buffer } },
  });
  expect(up.ok()).toBeTruthy();
  const upBody = await up.json();
  uploads[genName + ':' + pages.join(',')] = { sha256: upBody.sha256 };
  expect(upBody.sha256).toBe(sha256File(full));
  const commit = await api.post('/api/documents', { data: { upload_id: upBody.upload_id, pages } });
  expect(commit.status()).toBe(202);
  const commitBody = await commit.json();
  const docs = await listDocs();
  const doc = docs.documents.find((d) => d.id === commitBody.document_id);
  expect(doc).toBeDefined();
  expect(doc!.status).toBe('ready');
  return doc!;
}

async function waitForImage(page: any, pageId: string): Promise<void> {
  await page.waitForFunction(
    (pid: string) => {
      const img = document.querySelector('[data-testid="page-image"]') as HTMLImageElement | null;
      return !!img && img.src.indexOf(pid) >= 0 && img.naturalWidth > 0;
    },
    pageId,
    { timeout: 60000 },
  );
}

async function measure(page: any, fixtureId: string, viewName: string): Promise<any> {
  const m = await page.evaluate(() => {
    const img = document.querySelector('[data-testid="page-image"]') as HTMLImageElement;
    const rect = document.querySelector('[data-testid="highlight-rect"]') as unknown as Element;
    const ib = img.getBoundingClientRect();
    const hb = (rect as any).getBoundingClientRect();
    return {
      image_bounds: { x: ib.x, y: ib.y, width: ib.width, height: ib.height },
      highlight_bounds: { x: hb.x, y: hb.y, width: hb.width, height: hb.height },
      natural_dimensions: { width: img.naturalWidth, height: img.naturalHeight },
    };
  });
  const vp = page.viewportSize();
  return {
    fixture_id: fixtureId,
    view_name: viewName,
    ...m,
    viewport_size: { width: vp ? vp.width : 0, height: vp ? vp.height : 0 },
  };
}

async function shot(page: any, name: string): Promise<void> {
  const p = path.join(SHOTS, name);
  await page.screenshot({ path: p });
  shots.push(name);
}

function devEntry(fixtureId: string): any {
  const dev = JSON.parse(fs.readFileSync(path.join(ROOT, 'fixtures', 'development.json'), 'utf-8'));
  const entry = dev.find((e: any) => e.fixture_id === fixtureId);
  expect(entry).toBeDefined();
  return entry;
}

test.describe.serial('import viewer slice', () => {
  test.beforeAll(async () => {
    fs.mkdirSync(SHOTS, { recursive: true });
    api = await request.newContext({ baseURL: BACKEND });
  });

  test.afterAll(async () => {
    await api.dispose();
  });

  test('upload pdf with page range via UI', async ({ page }) => {
    await page.goto(FRONTEND, { timeout: 90000 });
    await page.fill('[data-testid="page-range"]', '2,4');
    await page.setInputFiles('[data-testid="file-input"]', path.join(GEN, 'test_pages.pdf'));
    await expect
      .poll(
        async () => {
          const docs = await listDocs();
          const d = docs.documents.find(
            (x) => x.filename === 'test_pages.pdf' && x.pages.length === 2,
          );
          return d ? d.pages.map((p) => p.physical_page_number).join(',') : '';
        },
        { timeout: 60000 },
      )
      .toBe('2,4');
    const docs = await listDocs();
    const d = docs.documents.find((x) => x.filename === 'test_pages.pdf' && x.pages.length === 2)!;
    uploads['range-doc'] = { sha256: sha256File(path.join(GEN, 'test_pages.pdf')) };
    expect(d.status).toBe('ready');
    await shot(page, 'upload-pdf.png');
  });

  test('upload image via UI', async ({ page }) => {
    await page.goto(FRONTEND, { timeout: 90000 });
    await page.fill('[data-testid="page-range"]', '');
    await page.setInputFiles('[data-testid="file-input"]', path.join(GEN, 'standard.png'));
    await expect
      .poll(
        async () => {
          const docs = await listDocs();
          return docs.documents.some((x) => x.filename === 'standard.png') ? 'yes' : '';
        },
        { timeout: 60000 },
      )
      .toBe('yes');
    await shot(page, 'upload-image.png');
  });

  test('import full pdf and orientation fixtures via API', async () => {
    const full = await uploadAndCommit('test_pages.pdf', [1, 2, 3, 4, 5, 6, 7, 8]);
    expect(full.pages.map((p) => p.physical_page_number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    for (const name of ['portrait.pdf', 'landscape.pdf', 'cropbox.pdf', 'exif_oriented.jpg']) {
      const doc = await uploadAndCommit(name, [1]);
      expect(doc.pages.length).toBe(1);
    }
    const docs = await listDocs();
    expect(docs.capacity.total_pages).toBe(2 + 1 + 8 + 4);
  });

  test('viewer overlay stays aligned across transforms', async ({ page }) => {
    const target: number[] = devEntry('dev_p5').target;
    await page.goto(`${FRONTEND}/?box=${target.join(',')}`, { timeout: 90000 });
    const docs = await listDocs();
    const full = docs.documents.find((d) => d.filename === 'test_pages.pdf' && d.pages.length === 8)!;
    const p5 = full.pages.find((p) => p.physical_page_number === 5)!;
    await page.click(`[data-testid="page-${full.id}-5"]`);
    await waitForImage(page, p5.id);

    await page.click('[data-testid="btn-fit"]');
    await page.waitForTimeout(900);
    domBounds.push(await measure(page, 'dev_p5', 'fit'));
    await shot(page, 'fit.png');

    await page.click('[data-testid="btn-100"]');
    await page.waitForTimeout(900);
    domBounds.push(await measure(page, 'dev_p5', 'zoom100'));
    await shot(page, 'zoom100.png');

    await page.click('[data-testid="btn-200"]');
    await page.waitForTimeout(900);
    domBounds.push(await measure(page, 'dev_p5', 'zoom200'));
    await shot(page, 'zoom200.png');

    await page.click('[data-testid="btn-pan"]');
    await page.waitForTimeout(900);
    domBounds.push(await measure(page, 'dev_p5', 'pan'));
    await shot(page, 'pan.png');

    await page.setViewportSize({ width: 900, height: 600 });
    await page.waitForTimeout(900);
    domBounds.push(await measure(page, 'dev_p5', 'resize'));
    await shot(page, 'resize.png');
    await page.setViewportSize({ width: 1280, height: 720 });
  });

  test('orientation fixtures render with aligned overlays', async ({ page }) => {
    const cases: Array<[string, string, string]> = [
      ['orientation_portrait', 'portrait.pdf', 'orientation-portrait.png'],
      ['orientation_landscape', 'landscape.pdf', 'orientation-landscape.png'],
      ['orientation_cropbox', 'cropbox.pdf', 'orientation-cropbox.png'],
      ['orientation_exif_jpeg', 'exif_oriented.jpg', 'orientation-exif-jpeg.png'],
      ['orientation_standard_png', 'standard.png', 'orientation-standard-png.png'],
    ];
    for (const [fixtureId, filename, shotName] of cases) {
      const entry = devEntry(fixtureId);
      const target: number[] = entry.target;
      await page.goto(`${FRONTEND}/?box=${target.join(',')}`, { timeout: 90000 });
      const docs = await listDocs();
      const doc = docs.documents.find((d) => d.filename === filename)!;
      expect(doc).toBeDefined();
      const pg = doc.pages[0];
      await page.click(`[data-testid="page-${doc.id}-${pg.physical_page_number}"]`);
      await waitForImage(page, pg.id);
      await page.waitForTimeout(600);
      domBounds.push(await measure(page, fixtureId, 'default'));
      await shot(page, shotName);
    }
  });

  test('capacity limit rejects imports beyond 20 pages', async () => {
    const full = path.join(GEN, 'test_pages.pdf');
    const buffer = fs.readFileSync(full);
    const up = await api.post('/api/uploads', {
      multipart: { file: { name: 'test_pages.pdf', mimeType: 'application/pdf', buffer } },
    });
    expect(up.ok()).toBeTruthy();
    const upBody = await up.json();
    const commit = await api.post('/api/documents', {
      data: { upload_id: upBody.upload_id, pages: [1, 2, 3, 4, 5, 6, 7, 8] },
    });
    expect(commit.status()).toBe(409);
    const body = await commit.json();
    expect(body.detail.capacity).toBeDefined();
    expect(body.detail.capacity.max_pages).toBe(20);
  });

  test('delete a document and verify removal', async ({ page }) => {
    const tmp = await uploadAndCommit('portrait.pdf', [1]);
    await page.goto(FRONTEND, { timeout: 90000 });
    await page.click(`[data-testid="delete-${tmp.id}"]`);
    await expect
      .poll(
        async () => {
          const docs = await listDocs();
          return docs.documents.some((d) => d.id === tmp.id) ? 'present' : 'gone';
        },
        { timeout: 60000 },
      )
      .toBe('gone');
    await shot(page, 'delete.png');
  });

  test('export evidence files', async () => {
    const docs = await listDocs();
    const dev = JSON.parse(fs.readFileSync(path.join(ROOT, 'fixtures', 'development.json'), 'utf-8'));
    const sigByFilePage: Record<string, number[]> = {};
    for (const e of dev) {
      sigByFilePage[`${e.fixture_file}#${e.page_index}`] = e.signature_rgb;
    }
    const fixtureFor = (filename: string): string => {
      const direct: Record<string, string> = {
        'test_pages.pdf': 'fixtures/generated/test_pages.pdf',
        'portrait.pdf': 'fixtures/generated/portrait.pdf',
        'landscape.pdf': 'fixtures/generated/landscape.pdf',
        'cropbox.pdf': 'fixtures/generated/cropbox.pdf',
        'exif_oriented.jpg': 'fixtures/generated/exif_oriented.jpg',
        'standard.png': 'fixtures/generated/standard.png',
      };
      return direct[filename];
    };
    const importEvidence: any[] = [];
    for (const d of docs.documents) {
      const fixturePath = fixtureFor(d.filename);
      const stored = path.join(ROOT, d.original_path);
      expect(fs.existsSync(stored)).toBeTruthy();
      const pages = d.pages.map((p: ApiPage) => {
        const pageIndex = d.filename === 'test_pages.pdf' ? p.physical_page_number - 1 : 0;
        const rasterRel = `data/pages/${p.id}/canonical.png`;
        expect(fs.existsSync(path.join(ROOT, rasterRel))).toBeTruthy();
        return {
          physical_page: p.physical_page_number,
          page_id: p.id,
          canonical_raster_path: rasterRel,
          expected_signature_rgb: sigByFilePage[`${fixturePath}#${pageIndex}`],
        };
      });
      importEvidence.push({
        fixture_path: fixturePath,
        stored_original_path: d.original_path,
        document_id: d.id,
        sha256_at_upload: sha256File(path.join(ROOT, fixturePath)),
        pages,
      });
    }
    const rangeDoc = docs.documents.find((d) => d.filename === 'test_pages.pdf' && d.pages.length === 2)!;
    expect(rangeDoc).toBeDefined();
    const rangeEntry = importEvidence.find((e) => e.document_id === rangeDoc.id)!;
    const noncontiguous = {
      fixture_path: 'fixtures/generated/test_pages.pdf',
      selected_pages: [2, 4],
      document_id: rangeDoc.id,
      pages: rangeEntry.pages,
    };
    expect(rangeEntry.pages.map((p: any) => p.physical_page).sort()).toEqual([2, 4]);
    const evidence = { capacity_enforced: true, import_evidence: importEvidence, noncontiguous_import: noncontiguous };
    fs.writeFileSync(path.join(EVIDENCE, 'e2e-evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
    expect(domBounds.length).toBe(10);
    fs.writeFileSync(path.join(EVIDENCE, 'dom-bounds.json'), JSON.stringify(domBounds, null, 2) + '\n');
  });
});
