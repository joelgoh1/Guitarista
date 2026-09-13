import * as React from "react";
import type { ChordVariation } from "@guitarista/music-theory";
import { cn } from "@/lib/utils";

export interface ChordDiagramProps {
  variation: ChordVariation;
  /** Number of fret rows to draw (grows if the voicing needs more). */
  fretsShown?: number;
  showFingers?: boolean;
  /** Pixel width, or `'responsive'` to fill the container. */
  size?: number | "responsive";
  /** Accessible title (also rendered as the SVG `<title>`). */
  title?: string;
  className?: string;
}

// viewBox geometry (all in user units).
const VB_W = 120;
const VB_H = 150;
const STRINGS = 6;
const X0 = 26; // low E column
const STRING_GAP = 15.6;
const Y0 = 32; // nut / first fret wire
const FRET_H = 22;
const DOT_R = 5.6;
const MARKER_Y = Y0 - 11;

/** x coordinate for a string number (1 = high E, rightmost). */
function stringX(s: number) {
  return X0 + (STRINGS - s) * STRING_GAP;
}

export interface FretWindow {
  /** First fret drawn under the top wire. 1 means the nut is shown. */
  startFret: number;
  /** Number of fret rows drawn. */
  frets: number;
  showNut: boolean;
}

/** Choose which slice of the neck to draw for a voicing. */
export function computeFretWindow(variation: ChordVariation, fretsShown: number): FretWindow {
  const frets = variation.positions.map((p) => p.fret).filter((f) => f > 0);
  if (variation.bar.hasBar && variation.bar.fret > 0) frets.push(variation.bar.fret);
  const maxFret = frets.length ? Math.max(...frets) : 0;
  const minFret = frets.length ? Math.min(...frets) : 1;
  if (maxFret <= fretsShown) return { startFret: 1, frets: fretsShown, showNut: true };
  const span = maxFret - minFret + 1;
  return { startFret: minFret, frets: Math.max(fretsShown, span), showNut: false };
}

/** Pure SVG chord diagram. Columns run low E (string 6) left → high E (string 1) right. */
export function ChordDiagram({
  variation,
  fretsShown = 5,
  showFingers = true,
  size = 160,
  title,
  className,
}: ChordDiagramProps) {
  const titleId = React.useId();
  const window = computeFretWindow(variation, fretsShown);
  const height = Y0 + window.frets * FRET_H + 6;
  const vbH = Math.max(VB_H, height);

  const fretY = (fret: number) => Y0 + (fret - window.startFret) * FRET_H + FRET_H / 2;

  const played = new Set(variation.positions.map((p) => p.string));
  const openStrings = variation.positions.filter((p) => p.fret === 0).map((p) => p.string);
  const dots = variation.positions.filter((p) => p.fret > 0);
  const mutedStrings: number[] = [];
  for (let s = 1; s <= STRINGS; s++) if (!played.has(s)) mutedStrings.push(s);

  const barre = variation.bar.hasBar && variation.bar.fret > 0 ? variation.bar : null;
  // bar.top/bottom are string numbers; normalise so lo is the leftmost column.
  const barLeft = barre ? stringX(Math.max(barre.top, barre.bottom)) : 0;
  const barRight = barre ? stringX(Math.min(barre.top, barre.bottom)) : 0;

  const gridLeft = stringX(STRINGS);
  const gridRight = stringX(1);
  const gridBottom = Y0 + window.frets * FRET_H;

  const sizeProps =
    size === "responsive"
      ? { width: "100%", height: undefined }
      : { width: size, height: Math.round((size * vbH) / VB_W) };

  const label = title ?? "Chord diagram";

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${vbH}`}
      role="img"
      aria-labelledby={titleId}
      data-slot="chord-diagram"
      className={cn("select-none", size === "responsive" && "h-auto w-full", className)}
      {...sizeProps}
    >
      <title id={titleId}>{label}</title>

      {/* fret position label */}
      {!window.showNut ? (
        <text
          x={gridLeft - 8}
          y={fretY(window.startFret) + 3.5}
          textAnchor="end"
          fontSize={9}
          fontFamily="var(--font-mono)"
          className="fill-muted-foreground"
          data-role="fret-label"
        >
          {window.startFret}fr
        </text>
      ) : null}

      {/* nut or top wire */}
      <rect
        x={gridLeft - 0.5}
        y={Y0 - (window.showNut ? 3 : 0.5)}
        width={gridRight - gridLeft + 1}
        height={window.showNut ? 3.5 : 1}
        rx={0.5}
        className={window.showNut ? "fill-fret-open" : "fill-fret-wire"}
        data-role="nut"
      />

      {/* fret wires */}
      {Array.from({ length: window.frets }, (_, i) => (
        <line
          key={`f${i}`}
          x1={gridLeft}
          x2={gridRight}
          y1={Y0 + (i + 1) * FRET_H}
          y2={Y0 + (i + 1) * FRET_H}
          strokeWidth={1}
          className="stroke-fret-wire"
        />
      ))}

      {/* strings */}
      {Array.from({ length: STRINGS }, (_, i) => {
        const s = STRINGS - i;
        const x = stringX(s);
        return (
          <line
            key={`s${s}`}
            x1={x}
            x2={x}
            y1={Y0}
            y2={gridBottom}
            strokeWidth={s >= 5 ? 1.4 : s >= 3 ? 1.1 : 0.8}
            className="stroke-fret-wire"
          />
        );
      })}

      {/* open / muted markers above the nut */}
      {openStrings.map((s) => (
        <circle
          key={`o${s}`}
          cx={stringX(s)}
          cy={MARKER_Y}
          r={3.4}
          fill="none"
          strokeWidth={1.3}
          className="stroke-fret-open"
          data-role="open"
        />
      ))}
      {mutedStrings.map((s) => {
        const x = stringX(s);
        const d = 3.2;
        return (
          <g key={`m${s}`} data-role="muted" className="stroke-fret-muted" strokeWidth={1.3}>
            <line x1={x - d} y1={MARKER_Y - d} x2={x + d} y2={MARKER_Y + d} />
            <line x1={x - d} y1={MARKER_Y + d} x2={x + d} y2={MARKER_Y - d} />
          </g>
        );
      })}

      {/* barre */}
      {barre ? (
        <rect
          x={barLeft - DOT_R}
          y={fretY(barre.fret) - DOT_R * 0.8}
          width={barRight - barLeft + DOT_R * 2}
          height={DOT_R * 1.6}
          rx={DOT_R * 0.8}
          className="fill-fret-dot"
          opacity={0.85}
          data-role="barre"
        />
      ) : null}

      {/* dots */}
      {dots.map((p) => {
        const cx = stringX(p.string);
        const cy = fretY(p.fret);
        return (
          <g key={`d${p.string}`} data-role="dot">
            <circle cx={cx} cy={cy} r={DOT_R} className="fill-fret-dot" />
            {showFingers && p.finger > 0 ? (
              <text
                x={cx}
                y={cy + 3}
                textAnchor="middle"
                fontSize={7.5}
                fontWeight={600}
                className="fill-fret-dot-foreground"
              >
                {p.finger}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}
