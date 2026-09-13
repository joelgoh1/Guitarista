"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { getAllChords, getChord, variationList } from "@guitarista/music-theory";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { ChordDiagram } from "@/components/chords/ChordDiagram";
import { shortChordName, typeLabel } from "@/components/chords/labels";
import type { ProgressionStep } from "@/components/practice/types";

/** Smallest integer suffix not yet used by an existing step id (pure, so safe in render). */
function nextStepId(steps: ProgressionStep[]) {
  let max = 0;
  for (const s of steps) {
    const n = Number(s.id.split("-").at(-1));
    if (Number.isFinite(n)) max = Math.max(max, n);
  }
  return max + 1;
}

export interface ProgressionEditorProps {
  steps: ProgressionStep[];
  onChange: (steps: ProgressionStep[]) => void;
  activeIndex?: number | null;
  disabled?: boolean;
}

export function ProgressionEditor({ steps, onChange, activeIndex, disabled }: ProgressionEditorProps) {
  const [open, setOpen] = React.useState(false);
  const all = React.useMemo(() => getAllChords(), []);

  const update = (i: number, patch: Partial<ProgressionStep>) =>
    onChange(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const move = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= steps.length) return;
    const next = [...steps];
    [next[i], next[j]] = [next[j]!, next[i]!];
    onChange(next);
  };
  const remove = (i: number) => onChange(steps.filter((_, j) => j !== i));
  const add = (type: ProgressionStep["type"], key: ProgressionStep["key"]) => {
    onChange([...steps, { id: `${type}-${key}-${nextStepId(steps)}`, type, key, variation: 0, beats: 4 }]);
    setOpen(false);
  };

  return (
    <div data-slot="progression-editor" className="flex flex-col gap-3">
      <ol className="flex flex-col gap-2">
        {steps.map((s, i) => {
          const entry = getChord(s.type, s.key);
          const variations = variationList(entry);
          const v = variations[Math.min(s.variation, variations.length - 1)]!;
          return (
            <li
              key={s.id}
              data-active={i === activeIndex ? "true" : undefined}
              className="flex items-center gap-3 rounded-lg border border-border bg-card p-2 data-[active=true]:border-primary data-[active=true]:bg-primary/5"
            >
              <span className="w-5 text-center font-mono text-xs text-muted-foreground">{i + 1}</span>
              <ChordDiagram variation={v} size={44} showFingers={false} title={entry.name} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{entry.name}</p>
                {variations.length > 1 ? (
                  <select
                    aria-label={`Voicing for ${entry.name}`}
                    className="mt-0.5 h-6 rounded-md border border-input bg-transparent px-1 text-xs text-muted-foreground"
                    value={s.variation}
                    disabled={disabled}
                    onChange={(e) => update(i, { variation: Number(e.target.value) })}
                  >
                    {variations.map((_, vi) => (
                      <option key={vi} value={vi}>
                        Voicing {vi + 1}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="text-xs text-muted-foreground">{typeLabel(s.type)}</p>
                )}
              </div>
              <label className="flex items-center gap-1 text-xs text-muted-foreground">
                <Input
                  type="number"
                  min={1}
                  max={8}
                  aria-label={`Beats for ${entry.name}`}
                  className="h-7 w-14 text-center"
                  value={s.beats}
                  disabled={disabled}
                  onChange={(e) => {
                    const n = Math.min(8, Math.max(1, Number(e.target.value) || 1));
                    update(i, { beats: n });
                  }}
                />
                beats
              </label>
              <div className="flex items-center">
                <Button size="icon-xs" variant="ghost" aria-label="Move up" disabled={disabled || i === 0} onClick={() => move(i, -1)}>
                  <ArrowUp />
                </Button>
                <Button size="icon-xs" variant="ghost" aria-label="Move down" disabled={disabled || i === steps.length - 1} onClick={() => move(i, 1)}>
                  <ArrowDown />
                </Button>
                <Button size="icon-xs" variant="ghost" aria-label={`Remove ${entry.name}`} disabled={disabled} onClick={() => remove(i)}>
                  <Trash2 />
                </Button>
              </div>
            </li>
          );
        })}
      </ol>

      <Button variant="outline" size="sm" onClick={() => setOpen(true)} disabled={disabled} className="self-start">
        <Plus data-icon="inline-start" />
        Add chord
      </Button>

      <CommandDialog open={open} onOpenChange={setOpen} title="Add chord" description="Search chords by name">
        <Command>
          <CommandInput placeholder="Search chords…" autoFocus />
          <CommandList>
          <CommandEmpty>No chord found.</CommandEmpty>
          <CommandGroup heading="Chords">
            {all.map((c) => (
              <CommandItem
                key={`${c.type}-${c.key}`}
                value={`${c.entry.name} ${shortChordName(c.type, c.key)}`}
                onSelect={() => add(c.type, c.key)}
              >
                <span className="w-10 font-mono text-xs text-muted-foreground">{shortChordName(c.type, c.key)}</span>
                <span>{c.entry.name}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {Object.keys(c.entry.variations).length} voicings
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
          </CommandList>
        </Command>
      </CommandDialog>
    </div>
  );
}
