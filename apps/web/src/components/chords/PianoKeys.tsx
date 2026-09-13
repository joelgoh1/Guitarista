"use client";

import * as React from "react";
import { midiToNote, parseNote } from "@guitarista/music-theory";
import { cn } from "@/lib/utils";

export interface PianoKeysProps {
  /** Note names to highlight (scientific pitch, `♯`/`♭` accepted). */
  highlighted: string[];
  /** Note that gets the strongest highlight; defaults to the lowest highlighted note. */
  root?: string;
  from?: string;
  to?: string;
  showLabels?: boolean;
  onKeyClick?: (note: string, midi: number) => void;
  className?: string;
}

const WHITE_W = 14;
const WHITE_H = 64;
const BLACK_W = 8.5;
const BLACK_H = 40;
const BLACK_PCS = new Set([1, 3, 6, 8, 10]);

function isBlack(midi: number) {
  return BLACK_PCS.has(midi % 12);
}

function safeMidi(name: string): number | null {
  try {
    return parseNote(name).midi;
  } catch {
    return null;
  }
}

/** SVG piano keyboard; the range extends automatically to include highlighted notes. */
export function PianoKeys({
  highlighted,
  root,
  from = "C2",
  to = "C5",
  showLabels = false,
  onKeyClick,
  className,
}: PianoKeysProps) {
  const highlightedMidi = highlighted.map(safeMidi).filter((m): m is number => m !== null);
  let lo = parseNote(from).midi;
  let hi = parseNote(to).midi;
  if (highlightedMidi.length) {
    lo = Math.min(lo, Math.floor(Math.min(...highlightedMidi) / 12) * 12);
    hi = Math.max(hi, Math.ceil((Math.max(...highlightedMidi) + 1) / 12) * 12);
  }
  const rootMidi = root ? safeMidi(root) : highlightedMidi.length ? Math.min(...highlightedMidi) : null;
  const set = new Set(highlightedMidi);

  const keys: { midi: number; black: boolean; x: number }[] = [];
  let whiteIndex = 0;
  for (let m = lo; m <= hi; m++) {
    if (isBlack(m)) {
      keys.push({ midi: m, black: true, x: whiteIndex * WHITE_W - BLACK_W / 2 });
    } else {
      keys.push({ midi: m, black: false, x: whiteIndex * WHITE_W });
      whiteIndex++;
    }
  }
  const width = whiteIndex * WHITE_W;
  const interactive = !!onKeyClick;

  const renderKey = (k: { midi: number; black: boolean; x: number }) => {
    const on = set.has(k.midi);
    const isRoot = on && k.midi === rootMidi;
    const name = midiToNote(k.midi);
    const common = {
      "data-midi": k.midi,
      "data-note": name,
      "data-highlighted": on ? "true" : undefined,
      "data-root": isRoot ? "true" : undefined,
      onClick: interactive ? () => onKeyClick?.(name, k.midi) : undefined,
      className: cn(
        "transition-colors",
        interactive && "cursor-pointer",
        k.black ? "fill-piano-black" : "fill-piano-white",
        on && "fill-piano-highlight",
      ),
      opacity: on && !isRoot ? 0.75 : 1,
      role: interactive ? ("button" as const) : undefined,
      tabIndex: interactive ? 0 : undefined,
      "aria-label": interactive ? name : undefined,
    };
    return k.black ? (
      <rect
        key={k.midi}
        x={k.x}
        y={0}
        width={BLACK_W}
        height={BLACK_H}
        rx={1.2}
        stroke="var(--background)"
        strokeWidth={0.6}
        {...common}
      />
    ) : (
      <g key={k.midi}>
        <rect
          x={k.x}
          y={0}
          width={WHITE_W}
          height={WHITE_H}
          rx={1.5}
          stroke="var(--border)"
          strokeWidth={0.8}
          {...common}
        />
        {showLabels && k.midi % 12 === 0 ? (
          <text
            x={k.x + WHITE_W / 2}
            y={WHITE_H - 4}
            textAnchor="middle"
            fontSize={5.5}
            fontFamily="var(--font-mono)"
            className="fill-muted-foreground pointer-events-none"
          >
            {name}
          </text>
        ) : null}
      </g>
    );
  };

  return (
    <svg
      viewBox={`0 0 ${width} ${WHITE_H}`}
      role="img"
      aria-label={
        highlighted.length ? `Piano keys highlighting ${highlighted.join(", ")}` : "Piano keys"
      }
      data-slot="piano-keys"
      className={cn("h-auto w-full select-none", className)}
    >
      {keys.filter((k) => !k.black).map(renderKey)}
      {keys.filter((k) => k.black).map(renderKey)}
    </svg>
  );
}
