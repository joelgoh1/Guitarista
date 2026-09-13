"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "motion/react";
import {
  variationHasBarre,
  variationList,
  variationToMidi,
  type FlatChord,
} from "@guitarista/music-theory";
import { Badge } from "@/components/ui/badge";
import { ChordDiagram } from "@/components/chords/ChordDiagram";
import { ChordPlayButton } from "@/components/chords/ChordPlayButton";
import { chordHref, typeLabel } from "@/components/chords/labels";

export function ChordCard({ chord }: { chord: FlatChord }) {
  const variations = variationList(chord.entry);
  const first = variations[0]!;
  const href = chordHref(chord.type, chord.key);
  const hasBarre = variations.some(variationHasBarre);

  return (
    <motion.article
      data-slot="chord-card"
      whileHover={{ y: -3 }}
      transition={{ type: "spring", stiffness: 400, damping: 28 }}
      className="group relative flex flex-col gap-3 rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm transition-colors hover:border-primary/40"
    >
      <Link
        href={href}
        className="flex flex-col items-center gap-2 rounded-lg outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        aria-label={`${chord.entry.name} voicings`}
      >
        <ChordDiagram
          variation={first}
          size={120}
          title={`${chord.entry.name}, variation 1`}
          className="text-foreground"
        />
      </Link>
      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold leading-tight">
            <Link href={href} className="after:absolute after:inset-0 after:rounded-xl">
              {chord.entry.name}
            </Link>
          </h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{typeLabel(chord.type)}</span>
            <span aria-hidden>·</span>
            <span>
              {variations.length} {variations.length === 1 ? "voicing" : "voicings"}
            </span>
            {hasBarre ? (
              <Badge variant="outline" className="h-4 px-1 text-[10px]">
                barre
              </Badge>
            ) : null}
          </p>
        </div>
        <ChordPlayButton
          midiNotes={variationToMidi(first)}
          size="icon-sm"
          variant="secondary"
          label={`Strum ${chord.entry.name}`}
          className="relative z-10 shrink-0"
        />
      </div>
    </motion.article>
  );
}
