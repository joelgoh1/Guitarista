"use client";

import * as React from "react";
import { Disc3, Layers } from "lucide-react";
import {
  CHORD_KEYS,
  SCALES,
  SCALE_LABELS,
  scaleNotes,
  scalePitchClasses,
  type ScaleId,
} from "@guitarista/music-theory";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Fretboard } from "@/components/chords/Fretboard";

const SCALE_IDS = Object.keys(SCALES) as ScaleId[];

export function ScaleExplorer() {
  const [rootPc, setRootPc] = React.useState(9); // A
  const [scale, setScale] = React.useState<ScaleId>("pentatonic_minor");
  const rootKey = CHORD_KEYS.find((k) => k.pitchClass === rootPc)!;
  const notes = scaleNotes(`${rootKey.label}3`, scale).map((n) => n.replace(/-?\d+$/u, ""));
  const pcs = scalePitchClasses(rootPc, scale);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Scale explorer</CardTitle>
        <CardDescription>Pick a key and a scale to see every position on the neck.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={rootPc} onValueChange={(v) => typeof v === "number" && setRootPc(v)} items={Object.fromEntries(CHORD_KEYS.map((k) => [k.pitchClass, k.label]))}>
            <SelectTrigger aria-label="Key" className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CHORD_KEYS.map((k) => (
                <SelectItem key={k.id} value={k.pitchClass}>
                  {k.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={scale} onValueChange={(v) => v && setScale(v as ScaleId)} items={SCALE_LABELS}>
            <SelectTrigger aria-label="Scale" className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCALE_IDS.map((id) => (
                <SelectItem key={id} value={id}>
                  {SCALE_LABELS[id]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <ul className="ml-auto flex flex-wrap gap-1.5">
            {notes.map((n, i) => (
              <li key={`${n}-${i}`}>
                <Badge variant={i === 0 ? "default" : "secondary"} className="font-mono">
                  {n}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
        <div className="overflow-x-auto">
          <Fretboard pitchClasses={pcs} root={rootPc} className="min-w-[560px]" />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled title="Coming soon">
            <Layers data-icon="inline-start" />
            Overlay on a progression
          </Button>
          <Button variant="outline" size="sm" disabled title="Coming soon">
            <Disc3 data-icon="inline-start" />
            Generate backing track
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
