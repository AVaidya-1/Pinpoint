import { Fragment, useEffect, useId, useRef, useState } from 'react';
import { GlassRenderer } from './glassGpu';

// "Liquid glass". Preferred path: a vgpu/WebGPU canvas behind the panel's
// content (glassGpu.ts). Fallback when WebGPU is unavailable: the backdrop is
// refracted near the edges by an SVG displacement map inside backdrop-filter,
// each colour channel bent by a different amount, then frosted. SVG backdrop
// filters only work in Chromium; other browsers get plain frost.
const CHROMIUM = typeof navigator !== 'undefined' && /Chrome\//.test(navigator.userAgent);

/** Displacement map for a sharp-cornered rectangle: pixels inside the bezel
 *  sample from further inside, like light bending through a thick glass edge. */
function edgeMap(w: number, h: number, bezel: number): string {
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';
  const img = ctx.createImageData(w, h);
  const ramp = (d: number) => (d >= bezel ? 0 : (1 - d / bezel) ** 2);
  for (let y = 0; y < h; y++) {
    const fy = ramp(y) - ramp(h - 1 - y);
    for (let x = 0; x < w; x++) {
      const fx = ramp(x) - ramp(w - 1 - x);
      const i = (y * w + x) * 4;
      img.data[i] = 128 + 127 * fx;
      img.data[i + 1] = 128 + 127 * fy;
      img.data[i + 2] = 128;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL();
}

export function useLiquidGlass<T extends HTMLElement>({ refraction = 16, aberration = 2, blur = 12 } = {}) {
  const [el, ref] = useState<T | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [mode, setMode] = useState<'pending' | 'gpu' | 'svg'>('pending');
  const id = `glass${useId().replace(/:/g, '')}`;
  const [map, setMap] = useState<{ w: number; h: number; url: string } | null>(null);

  // WebGPU renderer, if available.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!el || !canvas) return;
    const abort = new AbortController();
    let renderer: GlassRenderer | null = null;
    GlassRenderer.create(canvas, undefined, abort.signal).then((r) => {
      if (abort.signal.aborted) { r?.dispose(); return; }
      renderer = r;
      setMode(r ? 'gpu' : 'svg');
    });
    return () => { abort.abort(); renderer?.dispose(); };
  }, [el]);

  // SVG fallback.
  useEffect(() => {
    if (!el || mode !== 'svg' || !CHROMIUM) return;
    let last = '';
    const update = () => {
      const w = Math.round(el.offsetWidth);
      const h = Math.round(el.offsetHeight);
      if (!w || !h || `${w}x${h}` === last) return;
      last = `${w}x${h}`;
      setMap({ w, h, url: edgeMap(w, h, Math.min(14, h / 3)) });
    };
    const ro = new ResizeObserver(update);
    ro.observe(el);
    update();
    return () => ro.disconnect();
  }, [el, mode]);

  useEffect(() => {
    if (!el) return;
    const frost = `blur(${blur}px) saturate(1.4) brightness(0.4)`;
    const value = mode === 'gpu' ? 'none' : map ? `url(#${id}) ${frost}` : frost;
    el.style.backdropFilter = value;
    el.style.setProperty('-webkit-backdrop-filter', value);
  }, [el, map, id, blur, mode]);

  const layer = mode === 'svg' ? (map && (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
      <filter id={id} x="0" y="0" width={map.w} height={map.h} filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
        <feImage href={map.url} x="0" y="0" width={map.w} height={map.h} preserveAspectRatio="none" result="map" />
        {([['R', refraction + aberration, '1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0'],
          ['G', refraction, '0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0'],
          ['B', refraction - aberration, '0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0']] as const).map(([ch, scale, matrix]) => (
          <Fragment key={ch}>
            <feDisplacementMap in="SourceGraphic" in2="map" scale={scale} xChannelSelector="R" yChannelSelector="G" result={`d${ch}`} />
            <feColorMatrix in={`d${ch}`} type="matrix" values={matrix} result={ch} />
          </Fragment>
        ))}
        <feBlend in="R" in2="G" mode="screen" result="RG" />
        <feBlend in="RG" in2="B" mode="screen" />
      </filter>
    </svg>
  )) : <canvas ref={canvasRef} className="glass-gl" aria-hidden="true" />;

  /** Render `layer` as the first child of the glass element and add `cls` to its className. */
  return [ref, layer, mode === 'gpu' ? ' glass-gpu' : ''] as const;
}
