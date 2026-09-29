// Minimal stroke icons (Lucide-style paths, ISC license).
const PATHS: Record<string, string[]> = {
  plus: ['M12 5v14', 'M5 12h14'],
  minus: ['M5 12h14'],
  fit: ['M3 8V3h5', 'M16 3h5v5', 'M21 16v5h-5', 'M8 21H3v-5'],
  search: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z', 'm21 21-4.3-4.3'],
  up: ['m18 15-6-6-6 6'],
  down: ['m6 9 6 6 6-6'],
  eye: ['M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'],
  eyeOff: ['M9.9 4.2A10.4 10.4 0 0 1 12 4c6.5 0 10 8 10 8a18 18 0 0 1-2.2 3.2', 'M6.6 6.6A18 18 0 0 0 2 12s3.5 8 10 8a10 10 0 0 0 5.4-1.6', 'M14.1 14.1a3 3 0 1 1-4.2-4.2', 'm2 2 20 20'],
  back: ['m15 18-6-6 6-6'],
  close: ['M18 6 6 18', 'm6 6 12 12'],
  send: ['M12 19V5', 'm5 12 7-7 7 7'],
  file: ['M14 2H4v20h16V8z', 'M14 2v6h6'],
  upload: ['M12 15V3', 'm7 8 5-5 5 5', 'M21 15v6H3v-6'],
  trash: ['M3 6h18', 'M8 6V4h8v2', 'M19 6l-1 14H6L5 6'],
  clock: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M12 6v6l4 2'],
  target: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12z', 'M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z'],
  zoomIn: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z', 'm21 21-4.3-4.3', 'M11 8v6', 'M8 11h6'],
  copy: ['M8 8h12v12H8z', 'M4 16V4h12'],
  left: ['m15 18-6-6 6-6'],
  right: ['m9 18 6-6-6-6'],
  panel: ['M3 4h18v16H3z', 'M9 4v16'],
  enter: ['M20 5v7H5', 'm9 8-4 4 4 4'],
};

export function Icon({ name, size = 16 }: { name: keyof typeof PATHS | string; size?: number }) {
  const paths = PATHS[name] ?? [];
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="square" strokeLinejoin="miter" aria-hidden="true" className="icon">
      {paths.map((d) => <path key={d} d={d} />)}
    </svg>
  );
}
