// WebGPU liquid glass (vgpu): the search dock is rendered as a physical slab
// of glass with sharp mitred bevels floating above the page. Optics follow the
// vgpu "Transmission" example: Snell refraction through the slab and the air
// gap below it, spectral dispersion (IOR spread across wavelengths), Beer-
// Lambert absorption, and a Fresnel-weighted studio environment reflection
// whose key light follows the pointer. The flat top face is frosted and its
// luminosity compressed (Apple's "regular" variant) so text on it stays legible.
//
// Per frame: page canvases + highlights under the slab -> texture -> separable
// Gaussian (half-res vgpu targets) -> slab composite onto the canvas.
import {
  effect, frame, init, sampler, surface, target, texture,
  type Effect, type Gpu, type Surface, type Target, type Texture,
} from 'vgpu';

export interface GlassLook {
  /** Index of refraction (window glass ~1.5). */
  ior: number;
  /** IOR spread across the visible spectrum; higher = stronger rainbow fringe on the bevels. */
  dispersion: number;
  /** Slab thickness, CSS px. */
  thickness: number;
  /** Air gap between the slab and the page, CSS px (more = stronger bevel lensing). */
  lift: number;
  /** Bevel width, CSS px, and slope (tan of the bevel angle). */
  bevel: number;
  slope: number;
  /** Blue-green body tint from absorption (0 = clear). */
  absorption: number;
  /** Frost sigma for the top face, CSS px. */
  blur: number;
  /** Brightest the top face may get (0-1). Lower = more legible text. */
  lumaMax: number;
}

export const DEFAULT_LOOK: GlassLook = {
  ior: 1.5, dispersion: 0.1, thickness: 34, lift: 26, bevel: 15, slope: 1.8,
  absorption: 0.5, blur: 9, lumaMax: 0.4,
};

// One axis of a separable Gaussian. step = one output texel in uv; sigma and
// radius are in steps.
const BLUR_SHADER = /* wgsl */ `
struct Blur { step: vec4f }  // step.xy, sigma, radius
@group(0) @binding(0) var<uniform> blur: Blur;
@group(0) @binding(1) var src: texture_2d<f32>;
@group(0) @binding(2) var samp: sampler;

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let s = blur.step.z;
  let n = i32(blur.step.w);
  var acc = textureSampleLevel(src, samp, uv, 0.0).rgb;
  var total = 1.0;
  for (var i = 1; i <= n; i++) {
    let fi = f32(i);
    let w = exp(-0.5 * fi * fi / (s * s));
    let o = blur.step.xy * fi;
    acc += (textureSampleLevel(src, samp, uv + o, 0.0).rgb + textureSampleLevel(src, samp, uv - o, 0.0).rgb) * w;
    total += 2.0 * w;
  }
  return vec4f(acc / total, 1.0);
}
`;

const COMPOSITE_SHADER = /* wgsl */ `
struct Params {
  box: vec4f,     // slab w, h (css px), capture margin, bevel width
  optics: vec4f,  // ior, thickness, air gap, dispersion spread
  light: vec4f,   // key light direction xyz, absorption
  look: vec4f,    // top luma max, bevel slope, -, -
}
@group(0) @binding(0) var<uniform> params: Params;
@group(0) @binding(1) var frosted: texture_2d<f32>;
@group(0) @binding(2) var sharp: texture_2d<f32>;
@group(0) @binding(3) var samp: sampler;

const SPECTRAL: i32 = 9;

fn to_uv(p: vec2f) -> vec2f {
  return (p + params.box.z) / (params.box.xy + 2.0 * params.box.z);
}

fn spectral_weight(t: f32) -> vec3f {
  return vec3f(
    exp(-pow((t - 0.05) / 0.45, 2.0)),
    exp(-pow((t - 0.50) / 0.38, 2.0)),
    exp(-pow((t - 0.95) / 0.45, 2.0)),
  );
}

fn dielectric_fresnel(ior: f32, facing: f32) -> f32 {
  let f0 = pow((ior - 1.0) / (ior + 1.0), 2.0);
  return f0 + (1.0 - f0) * pow(1.0 - facing, 5.0);
}

// Procedural studio: dark room, a tight key softbox where the pointer is, a
// broad overhead strip, and a faint floor bounce.
fn studio(r: vec3f, key: vec3f) -> vec3f {
  let k = pow(max(dot(r, key), 0.0), 48.0) * 2.4;
  let strip = pow(max(dot(r, normalize(vec3f(0.0, -1.0, 0.55))), 0.0), 6.0) * 0.45;
  let bounce = smoothstep(0.0, 1.0, r.y) * 0.05;
  return vec3f(0.018, 0.022, 0.03) + vec3f(0.92, 0.96, 1.0) * (k + strip) + vec3f(0.2, 0.3, 0.5) * bounce;
}

// Ray looking straight down enters the top face (normal n), crosses the slab,
// leaves through the flat bottom and travels the air gap to the page.
// Returns the page offset in px and the path length inside the glass (w < 0: TIR).
fn transmit(n: vec3f, ior: f32, thick: f32) -> vec3f {
  let inside = refract(vec3f(0.0, 0.0, -1.0), n, 1.0 / ior);
  let down = max(-inside.z, 1e-3);
  let through = inside.xy / down * thick;
  let out = refract(inside, vec3f(0.0, 0.0, 1.0), ior);
  if (dot(out, out) < 1e-6) { return vec3f(through, -1.0); }
  let gap = out.xy / max(-out.z, 1e-3) * params.optics.z;
  return vec3f(through + gap, thick / down);
}

// Luminosity adaptation: backdrop brightness mapped into a dark band, hue kept.
fn adapt(col: vec3f, top: f32) -> vec3f {
  let l = dot(col, vec3f(0.2126, 0.7152, 0.0722));
  let b = 0.06 + (top - 0.06) * l;
  let tinted = col * (b / max(l, 1e-3));
  return mix(vec3f(b), tinted, smoothstep(0.01, 0.08, l) * 0.9);
}

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let size = params.box.xy;
  let bev = params.box.w;
  let ior = params.optics.x;
  let key = normalize(params.light.xyz);
  let p = uv * size;

  // Mitred chamfer: the nearest edge owns the pixel, so corners get sharp
  // diagonal seams like a cut glass block.
  let dl = p.x;
  let dr = size.x - p.x;
  let dt = p.y;
  let db = size.y - p.y;
  let d = min(min(dl, dr), min(dt, db));
  var outward = vec2f(0.0, 1.0);
  if (d == dl) { outward = vec2f(-1.0, 0.0); }
  else if (d == dr) { outward = vec2f(1.0, 0.0); }
  else if (d == dt) { outward = vec2f(0.0, -1.0); }
  let on_bevel = 1.0 - smoothstep(bev - 0.75, bev + 0.75, d);
  let n = normalize(vec3f(outward * params.look.y * on_bevel, 1.0));
  let facing = n.z;

  // Transmission.
  let top = adapt(textureSampleLevel(frosted, samp, to_uv(p), 0.0).rgb, params.look.x);
  var transmitted = top;
  var path = params.optics.y;
  if (on_bevel > 0.001) {
    // The chamfer thins the slab toward its edge.
    let thick = params.optics.y * (1.0 - 0.5 * clamp(1.0 - d / bev, 0.0, 1.0));
    var acc = vec3f(0.0);
    var total = vec3f(0.0);
    for (var i = 0; i < SPECTRAL; i++) {
      let t = (f32(i) + 0.5) / f32(SPECTRAL);
      let tr = transmit(n, ior + (t - 0.5) * params.optics.w, thick);
      var c = vec3f(0.01, 0.015, 0.02); // total internal reflection reads dark
      if (tr.z > 0.0) {
        let q = to_uv(p + tr.xy);
        c = mix(textureSampleLevel(sharp, samp, q, 0.0).rgb, textureSampleLevel(frosted, samp, q, 0.0).rgb, 0.3);
        path = tr.z;
      }
      let w = spectral_weight(t);
      acc += c * w;
      total += w;
    }
    let bevel_col = adapt(acc / max(total, vec3f(1e-4)), 0.78);
    transmitted = mix(top, bevel_col, on_bevel);
  }
  // Beer-Lambert: red goes first, so glass seen edge-on turns blue-green. The
  // top face stays nearly neutral; the bevels carry the tint.
  transmitted *= exp(-vec3f(0.5, 0.14, 0.09) * params.light.w * (path / params.optics.y) * (0.12 + 0.88 * on_bevel));

  // Reflection.
  let r = reflect(vec3f(0.0, 0.0, -1.0), n);
  let fresnel = dielectric_fresnel(ior, facing) + on_bevel * 0.1;
  var col = mix(transmitted, studio(r, key), fresnel);

  // Specular glint on the bevels, and the cut lines (bevel ridge, outer arris)
  // catching the key light.
  let h = normalize(key + vec3f(0.0, 0.0, 1.0));
  col += pow(max(dot(n, h), 0.0), 90.0) * 0.8 * on_bevel;
  let lit = clamp(dot(normalize(vec3f(outward, 0.7)), key) * 0.5 + 0.5, 0.0, 1.0);
  let ridge = 1.0 - smoothstep(0.0, 1.0, abs(d - bev));
  let arris = 1.0 - smoothstep(0.0, 1.2, d);
  col += ridge * (0.05 + 0.3 * lit * lit);
  col += arris * (0.04 + 0.45 * lit * lit);

  return vec4f(clamp(col, vec3f(0.0), vec3f(1.0)), 1.0);
}
`;

let gpuPromise: Promise<Gpu | null> | null = null;
function sharedGpu(): Promise<Gpu | null> {
  gpuPromise ??= (async () => {
    if (typeof navigator === 'undefined' || !('gpu' in navigator)) return null;
    try {
      const gpu = await init();
      gpu.onError((e) => console.error('[liquid glass]', e));
      return gpu;
    } catch {
      return null;
    }
  })();
  return gpuPromise;
}

type Rect = { x: number; y: number; w: number; h: number };

function intersect(a: Rect, b: DOMRect): Rect | null {
  const x = Math.max(a.x, b.left);
  const y = Math.max(a.y, b.top);
  const r = Math.min(a.x + a.w, b.right);
  const btm = Math.min(a.y + a.h, b.bottom);
  return r > x && btm > y ? { x, y, w: r - x, h: btm - y } : null;
}

/** Paints what is behind `rect` (viewport css px) into ctx at `dpr`. */
function captureBackdrop(ctx: OffscreenCanvasRenderingContext2D, rect: Rect, dpr: number) {
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  const toDest = (r: Rect) => [(r.x - rect.x) * dpr, (r.y - rect.y) * dpr, r.w * dpr, r.h * dpr] as const;

  // Pages: white paper first (covers not-yet-rendered pages), then canvases.
  for (const page of document.querySelectorAll<HTMLElement>('.pdfViewer .page')) {
    const pr = page.getBoundingClientRect();
    if (pr.bottom < rect.y) continue;
    if (pr.top > rect.y + rect.h) break;
    const i = intersect(rect, pr);
    if (!i) continue;
    ctx.fillStyle = '#fff';
    ctx.fillRect(...toDest(i));
    for (const c of page.querySelectorAll('canvas')) {
      const cr = c.getBoundingClientRect();
      const ci = intersect(rect, cr);
      if (!ci || !c.width || !cr.width) continue;
      const sx = c.width / cr.width;
      const sy = c.height / cr.height;
      ctx.drawImage(c, (ci.x - cr.left) * sx, (ci.y - cr.top) * sy, ci.w * sx, ci.h * sy, ...toDest(ci));
    }
  }

  // Answer highlights (DOM overlays) so they glow through the glass too.
  for (const box of document.querySelectorAll<HTMLElement>('.pp-hl-box')) {
    const br = box.getBoundingClientRect();
    if (!intersect(rect, br)) continue;
    const [x, y, w, h] = toDest({ x: br.left, y: br.top, w: br.width, h: br.height });
    const group = box.parentElement;
    const alpha = group?.classList.contains('is-active') ? 1 : 0.45;
    if (group?.classList.contains('kind-text')) {
      ctx.fillStyle = `rgba(46, 125, 255, ${0.34 * alpha})`;
      ctx.fillRect(x, y, w, h);
    } else {
      ctx.fillStyle = `rgba(46, 125, 255, ${0.12 * alpha})`;
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = `rgba(46, 125, 255, ${alpha})`;
      ctx.lineWidth = 2 * dpr;
      ctx.strokeRect(x, y, w, h);
    }
  }
}

export class GlassRenderer {
  private gpu: Gpu;
  private canvas: HTMLCanvasElement;
  private surf: Surface;
  private blurH: Effect;
  private blurV: Effect;
  private composite: Effect;
  private half: Target;    // horizontal pass output
  private frosted: Target; // vertical pass output
  private tex: Texture | null = null;
  private texSize = '';
  private scratch = new OffscreenCanvas(1, 1);
  private ctx = this.scratch.getContext('2d')!;
  private raf = 0;
  private lastSig = '';
  private lastPaint = 0;
  private disposed = false;
  private pointer: { x: number; y: number } | null = null;
  look: GlassLook;

  private constructor(gpu: Gpu, canvas: HTMLCanvasElement, look: GlassLook) {
    this.gpu = gpu;
    this.canvas = canvas;
    this.look = look;
    const samp = sampler(gpu, { minFilter: 'linear', magFilter: 'linear', addressModeU: 'clamp-to-edge', addressModeV: 'clamp-to-edge' });
    this.surf = surface(gpu, canvas, { dpr: [1, 2], alphaMode: 'opaque' });
    this.half = target(gpu, { size: [1, 1], label: 'glass-blur-h' });
    this.frosted = target(gpu, { size: [1, 1], label: 'glass-blur-v' });
    this.blurH = effect(gpu, BLUR_SHADER, { label: 'glass-blur-h', set: { samp } });
    this.blurV = effect(gpu, BLUR_SHADER, { label: 'glass-blur-v', set: { samp, src: this.half } });
    this.composite = effect(gpu, COMPOSITE_SHADER, { label: 'glass-composite', set: { samp, frosted: this.frosted } });
    window.addEventListener('pointermove', this.onPointer, { passive: true });
    this.raf = requestAnimationFrame(this.tick);
  }

  /** Resolves null when WebGPU is unavailable (callers fall back to CSS/SVG). */
  static async create(canvas: HTMLCanvasElement, look: GlassLook = DEFAULT_LOOK, signal?: AbortSignal): Promise<GlassRenderer | null> {
    const gpu = await sharedGpu();
    if (!gpu || signal?.aborted || !canvas.isConnected) return null;
    try {
      return new GlassRenderer(gpu, canvas, look);
    } catch (e) {
      console.warn('Liquid glass: WebGPU setup failed, using CSS fallback.', e);
      return null;
    }
  }

  private onPointer = (e: PointerEvent) => {
    this.pointer = { x: e.clientX, y: e.clientY };
  };

  private tick = (now: number) => {
    if (this.disposed) return;
    this.raf = requestAnimationFrame(this.tick);
    if (document.hidden) return;
    const r = this.canvas.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    const container = document.querySelector('.pv-container');
    const sig = `${r.left},${r.top},${r.width},${r.height},${container?.scrollTop},${container?.scrollLeft},${container?.scrollWidth},${this.pointer?.x},${this.pointer?.y}`;
    // Repaint on movement, and a few times a second for async page renders.
    if (sig === this.lastSig && now - this.lastPaint < 250) return;
    this.lastSig = sig;
    this.lastPaint = now;
    try {
      this.paint(r);
    } catch (e) {
      console.warn('Liquid glass: frame failed.', e);
    }
  };

  private paint(r: DOMRect) {
    const L = this.look;
    const dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
    const margin = Math.ceil(L.thickness + L.lift * 1.6 + L.blur * 3 + 16);
    const bevel = Math.min(L.bevel, r.height / 4);
    const rect = { x: r.left - margin, y: r.top - margin, w: r.width + 2 * margin, h: r.height + 2 * margin };
    const W = Math.max(1, Math.round(rect.w * dpr));
    const H = Math.max(1, Math.round(rect.h * dpr));

    if (this.scratch.width !== W || this.scratch.height !== H) {
      this.scratch.width = W;
      this.scratch.height = H;
    }
    captureBackdrop(this.ctx, rect, dpr);

    // Blur at half resolution: a smooth Gaussian loses nothing there.
    const hw = Math.max(1, Math.ceil(W / 2));
    const hh = Math.max(1, Math.ceil(H / 2));
    if (this.texSize !== `${W}x${H}`) {
      const old = this.tex;
      this.tex = texture(this.gpu, {
        kind: '2d', size: [W, H], format: 'rgba8unorm',
        usage: ['texture_binding', 'copy_dst', 'render_attachment'], label: 'glass-backdrop',
      });
      this.texSize = `${W}x${H}`;
      this.blurH.set({ src: this.tex });
      this.composite.set({ sharp: this.tex });
      old?.destroy();
      this.half.resize([hw, hh]);
      this.frosted.resize([hw, hh]);
    }
    this.gpu.device.gpu.queue.copyExternalImageToTexture({ source: this.scratch }, { texture: this.tex!.gpu }, [W, H]);

    // Key light: from the pointer (hovering 260px above the page), else top-left.
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const key = this.pointer ? [this.pointer.x - cx, this.pointer.y - cy, 260] : [-0.45 * r.width, -220, 260];

    // Sigma in half-res output texels; radius 3 sigma.
    const sigma = (L.blur * dpr) / 2;
    const radius = Math.min(48, Math.ceil(sigma * 3));
    this.blurH.set({ blur: { step: [1 / hw, 0, sigma, radius] } });
    this.blurV.set({ blur: { step: [0, 1 / hh, sigma, radius] } });
    this.composite.set({
      params: {
        box: [r.width, r.height, margin, bevel],
        optics: [L.ior, L.thickness, L.lift, L.dispersion],
        light: [key[0], key[1], key[2], L.absorption],
        look: [L.lumaMax, L.slope, 0, 0],
      },
    });
    frame(this.gpu, (f) => {
      f.pass(this.half, this.blurH);
      f.pass(this.frosted, this.blurV);
      f.pass(this.surf, this.composite);
    });
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    window.removeEventListener('pointermove', this.onPointer);
    this.surf.dispose();
    this.tex?.destroy();
  }
}
