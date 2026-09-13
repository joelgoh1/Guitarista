import * as React from "react";
import { midiPitchClass, PITCH_CLASS_NAMES_SHARP, STANDARD_TUNING, type Tuning } from "@guitarista/music-theory";
import { cn } from "@/lib/utils";

export interface FretboardProps {
  /** Pitch classes (0..11) to highlight. */
  pitchClasses: readonly number[];
  /** Pitch class drawn as the root (stronger). */
  root?: number;
  frets?: number;
  tuning?: Tuning;
  showNoteNames?: boolean;
  className?: string;
}

const LEFT = 26;
const TOP = 14;
const FRET_W = 34;
const STRING_GAP = 16;

/** Horizontal fretboard: string 1 (high E) on top, nut at the left. */
export function Fretboard({
  pitchClasses,
  root,
  frets = 12,
  tuning = STANDARD_TUNING,
  showNoteNames = true,
  className,
}: FretboardProps) {
  const set = new Set(pitchClasses);
  const strings = tuning.length;
  const width = LEFT + (frets + 1) * FRET_W + 8;
  const height = TOP + (strings - 1) * STRING_GAP + 22;
  const fretX = (f: number) => LEFT + f * FRET_W;
  const stringY = (i: number) => TOP + i * STRING_GAP;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Fretboard"
      data-slot="fretboard"
      className={cn("h-auto w-full select-none", className)}
    >
      {/* nut */}
      <rect x={fretX(1) - 3} y={TOP - 4} width={3.5} height={(strings - 1) * STRING_GAP + 8} className="fill-fret-open" />
      {/* fret wires */}
      {Array.from({ length: frets }, (_, i) => (
        <line key={i} x1={fretX(i + 2)} x2={fretX(i + 2)} y1={TOP - 4} y2={TOP + (strings - 1) * STRING_GAP + 4} strokeWidth={1} className="stroke-fret-wire" />
      ))}
      {/* fret numbers */}
      {Array.from({ length: frets }, (_, i) => (
        <text key={i} x={fretX(i + 1) + FRET_W / 2} y={height - 6} textAnchor="middle" fontSize={7} fontFamily="var(--font-mono)" className="fill-muted-foreground">
          {i + 1}
        </text>
      ))}
      {/* strings */}
      {tuning.map((_, i) => (
        <line key={i} x1={fretX(1) - 3} x2={fretX(frets + 1)} y1={stringY(i)} y2={stringY(i)} strokeWidth={0.7 + i * 0.25} className="stroke-fret-wire" />
      ))}
      {/* notes */}
      {tuning.map((open, si) =>
        Array.from({ length: frets + 1 }, (_, f) => {
          const pc = midiPitchClass(open + f);
          if (!set.has(pc)) return null;
          const isRoot = pc === root;
          const cx = f === 0 ? fretX(0) + FRET_W / 2 : fretX(f) + FRET_W / 2;
          const cy = stringY(si);
          return (
            <g key={`${si}-${f}`} data-role={isRoot ? "root" : "note"}>
              <circle cx={cx} cy={cy} r={6} className={isRoot ? "fill-fret-dot" : "fill-fret-dot"} opacity={isRoot ? 1 : 0.55} />
              {showNoteNames ? (
                <text x={cx} y={cy + 2.5} textAnchor="middle" fontSize={6} fontWeight={600} className="fill-fret-dot-foreground">
                  {PITCH_CLASS_NAMES_SHARP[pc]}
                </text>
              ) : null}
            </g>
          );
        }),
      )}
    </svg>
  );
}
