"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, Dumbbell } from "lucide-react";
import {
  midiToNote,
  variationHasBarre,
  variationList,
  variationMutedStrings,
  variationToMidi,
  type ChordEntry,
  type ChordKeyId,
  type ChordTypeId,
} from "@guitarista/music-theory";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChordDiagram } from "@/components/chords/ChordDiagram";
import { ChordPlayButton } from "@/components/chords/ChordPlayButton";
import { PianoKeys } from "@/components/chords/PianoKeys";
import { VariationPicker } from "@/components/chords/VariationPicker";
import {
  adjacentKey,
  chordHref,
  keyFlatLabel,
  keyLabel,
  shortChordName,
} from "@/components/chords/labels";

export interface ChordDetailProps {
  type: ChordTypeId;
  key_: ChordKeyId;
  entry: ChordEntry;
}

const STRING_NAMES = ["e", "B", "G", "D", "A", "E"]; // string 1..6

export function ChordDetail({ type, key_: key, entry }: ChordDetailProps) {
  const variations = React.useMemo(() => variationList(entry), [entry]);
  const [index, setIndex] = React.useState(0);
  const variation = variations[Math.min(index, variations.length - 1)]!;
  const midi = variationToMidi(variation);
  const soundingNotes = midi.map((m) => midiToNote(m));
  const muted = variationMutedStrings(variation);
  const prev = adjacentKey(key, -1);
  const next = adjacentKey(key, 1);
  const flat = keyFlatLabel(key);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <VariationPicker variations={variations} value={index} onChange={setIndex} />
        <nav aria-label="Neighbouring keys" className="flex items-center gap-1">
          <Link
            href={chordHref(type, prev)}
            className={buttonVariants({ variant: "outline", size: "sm" })}
            aria-label={`Previous key: ${shortChordName(type, prev)}`}
          >
            <ChevronLeft data-icon="inline-start" />
            {shortChordName(type, prev)}
          </Link>
          <Link
            href={chordHref(type, next)}
            className={buttonVariants({ variant: "outline", size: "sm" })}
            aria-label={`Next key: ${shortChordName(type, next)}`}
          >
            {shortChordName(type, next)}
            <ChevronRight data-icon="inline-end" />
          </Link>
        </nav>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_1fr]">
        <Card className="items-center">
          <CardContent className="flex w-full flex-col items-center gap-4">
            <ChordDiagram
              variation={variation}
              size="responsive"
              title={`${entry.name}, voicing ${index + 1}`}
              className="max-w-64"
            />
            <div className="flex flex-wrap items-center justify-center gap-2">
              <ChordPlayButton midiNotes={midi} mode="strum" variant="default">
                Strum
              </ChordPlayButton>
              <ChordPlayButton midiNotes={midi} mode="block" variant="secondary">
                Block
              </ChordPlayButton>
              <ChordPlayButton
                midiNotes={midi}
                mode="strum"
                variant="ghost"
                strumOptions={{ direction: "up", spreadMs: 30 }}
                label="Strum up"
              >
                Up
              </ChordPlayButton>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>On the piano</CardTitle>
              <CardDescription>
                The same notes as they fall on a keyboard; the root is brighter.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <PianoKeys highlighted={soundingNotes} showLabels />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Notes</CardTitle>
              <CardDescription>
                {entry.name}
                {flat ? ` (also written ${flat}${type === "minor" ? " minor" : ""})` : ""} — low to
                high.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <ul className="flex flex-wrap gap-2">
                {soundingNotes.map((n, i) => (
                  <li key={`${n}-${i}`}>
                    <Badge variant={i === 0 ? "default" : "secondary"} className="font-mono">
                      {n}
                    </Badge>
                  </li>
                ))}
              </ul>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                <dt className="text-muted-foreground">Fingering</dt>
                <dd className="font-mono">
                  {[...variation.positions]
                    .sort((a, b) => b.string - a.string)
                    .map((p) => `${STRING_NAMES[p.string - 1]}:${p.fret}`)
                    .join("  ")}
                </dd>
                <dt className="text-muted-foreground">Barre</dt>
                <dd>
                  {variationHasBarre(variation)
                    ? `fret ${variation.bar.fret}, strings ${variation.bar.top}–${variation.bar.bottom}`
                    : "none"}
                </dd>
                <dt className="text-muted-foreground">Not played</dt>
                <dd>{muted.length ? muted.map((s) => STRING_NAMES[s - 1]).join(", ") : "all strings ring"}</dd>
                <dt className="text-muted-foreground">Key</dt>
                <dd>
                  {keyLabel(key)}
                  {flat ? ` / ${flat}` : ""}
                </dd>
              </dl>
              <div>
                <Link href="/practice" className={buttonVariants({ variant: "outline", size: "sm" })}>
                  <Dumbbell data-icon="inline-start" />
                  Practise in a progression
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
