/**
 * Bridge CSS tokens (oklch in globals.css) to alphaTab `Color` values.
 *
 * alphaTab's `Color.fromJson` only understands #hex / rgb() / rgba(), and
 * Chromium returns oklch() verbatim from getComputedStyle, so we let the
 * canvas 2D context normalise any CSS color into 8-bit RGBA.
 */
export interface Rgba {
  r: number;
  g: number;
  b: number;
  a: number;
}

let ctx: CanvasRenderingContext2D | null | undefined;

function getCtx(): CanvasRenderingContext2D | null {
  if (ctx !== undefined) return ctx;
  if (typeof document === "undefined") return (ctx = null);
  const canvas = document.createElement("canvas");
  canvas.width = 1;
  canvas.height = 1;
  ctx = canvas.getContext("2d", { willReadFrequently: true });
  return ctx;
}

export function cssColorToRgba(color: string, fallback: Rgba): Rgba {
  const c = getCtx();
  if (!c || !color) return fallback;
  c.clearRect(0, 0, 1, 1);
  c.fillStyle = "#000";
  c.fillStyle = color; // invalid strings are ignored by the canvas, leaving #000
  c.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = c.getImageData(0, 0, 1, 1).data;
  return { r: r ?? 0, g: g ?? 0, b: b ?? 0, a: a ?? 255 };
}

/** Read a CSS custom property from the document root and convert it. */
export function readTokenRgba(token: string, fallback: Rgba): Rgba {
  if (typeof window === "undefined") return fallback;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  return cssColorToRgba(raw, fallback);
}
