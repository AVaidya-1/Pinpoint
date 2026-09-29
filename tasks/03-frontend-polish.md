# Task 3: Frontend Polish & TypeScript Fixes

## Goal
Ensure the frontend builds cleanly, handles all UI states from the spec, and works well for technical documentation with tons of diagrams and images.

## Context
Frontend is React + TypeScript + Vite in `frontend/`. Components: App.tsx, DocumentList.tsx (upload with drag-drop and page range selection), QuestionBar.tsx (search with progress polling and cancel), EvidenceList.tsx (result cards with crop previews), PageViewer.tsx (zoomable page viewer with SVG highlight overlay using react-zoom-pan-pinch). Styles in App.css.

The Vite dev server proxies `/api` to the backend at port 8000. Config is in `vite.config.ts`.

## Steps

### 1. Fix TypeScript build

Run:
```
cd frontend && npx tsc --noEmit
```

Fix any type errors. Common issues:
- Missing type annotations on event handlers
- `any` types that should be properly typed
- Missing null checks

### 2. Verify all UI states from Section 7 of the spec

Check that these states are properly handled in the UI:

**Outcome wording** (in QuestionBar.tsx `outcomeWording()`):
- `found` → "Found source regions. Checked X of X pages."
- `no_evidence` → "I couldn't identify supporting evidence in these X pages."
- `uncertain` → "I couldn't confidently locate a supporting region. Inspect the pages directly."
- `incomplete` → "Search incomplete: checked X of Y pages."
- `cancelled` → "Search cancelled: checked X of Y pages."

**Error states**:
- Missing API key → "Add a Gemini API key to the backend environment, then restart."
- Quota exhausted → "Model quota reached. Your documents and completed checks are saved."
- Backend unreachable → proper fallback message
- Upload too large (413) → user-friendly message
- Unsupported file (415) → user-friendly message

### 3. Verify viewer geometry

The PageViewer must:
- Show the page image at its natural pixel size
- Use an SVG overlay with `viewBox` matching the image dimensions
- Highlight boxes are in normalized [0,1] coordinates, scaled to image pixels
- Fit/100%/200% zoom buttons work correctly
- Pan works via react-zoom-pan-pinch
- The highlight toggle (Show/Hide) works
- Multiple highlight rectangles from the same evidence group display correctly
- Highlights use translucent yellow fill + red border (per spec)

### 4. Verify evidence list

The EvidenceList must:
- Show crop previews using CSS overflow (not fetching a separate crop image)
- Display filename, physical page number, and content type label
- Clicking a card opens the corresponding page with its highlight boxes
- Empty state shows helpful message

### 5. Verify responsive layout

Check the CSS media queries:
- At 900px width: sidebar stacks above viewer
- At 600px width: search input wraps, padding reduces
- No horizontal overflow at any width

### 6. Verify the document list

The DocumentList must:
- File chooser accepts PDF, PNG, JPG
- Drag-and-drop works
- Page range field (e.g., "1-4,7") is parsed correctly
- Capacity display shows "X/20 pages · Y left"
- Page chips are clickable to navigate viewer
- Remove button (×) deletes document and refreshes
- Error messages are user-friendly

### 7. Add the `tsconfig.json` strict mode check

Ensure `frontend/tsconfig.json` has reasonable strict settings. If it only has bare defaults, add:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"]
}
```

## Success Criteria
- `npx tsc --noEmit` passes with no errors
- `npx vite build` produces a working build
- All UI states match the spec wording exactly
- Viewer geometry renders correctly at all zoom levels
- Layout works at desktop, tablet (900px), and mobile (600px) widths
