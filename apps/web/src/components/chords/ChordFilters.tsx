"use client";

import * as React from "react";
import { Search, X } from "lucide-react";
import { useQueryStates } from "nuqs";
import { CHORD_KEYS, CHORD_TYPES } from "@guitarista/music-theory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { chordSearchParsers } from "@/components/chords/chordSearchParams";

export function useChordFilters() {
  return useQueryStates(chordSearchParsers, { clearOnDefault: true });
}

export function ChordFilters({ resultCount }: { resultCount: number }) {
  const [filters, setFilters] = useChordFilters();
  const active = filters.type || filters.key || filters.q || filters.barre;

  return (
    <div data-slot="chord-filters" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-48 flex-1 sm:max-w-xs">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Search chords"
            placeholder="Search chords…"
            value={filters.q}
            onChange={(e) => setFilters({ q: e.target.value })}
            className="pl-8"
          />
        </div>

        <ToggleGroup
          aria-label="Chord type"
          value={filters.type ? [filters.type] : []}
          onValueChange={(v) => setFilters({ type: (v[0] as typeof filters.type) ?? null })}
          variant="outline"
          size="sm"
          spacing={0}
        >
          {CHORD_TYPES.map((t) => (
            <ToggleGroupItem key={t.id} value={t.id} aria-label={t.label}>
              {t.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        <ToggleGroup
          aria-label="Barre"
          value={filters.barre ? [filters.barre] : []}
          onValueChange={(v) => setFilters({ barre: (v[0] as typeof filters.barre) ?? null })}
          variant="outline"
          size="sm"
          spacing={0}
        >
          <ToggleGroupItem value="yes">Barre</ToggleGroupItem>
          <ToggleGroupItem value="no">No barre</ToggleGroupItem>
        </ToggleGroup>

        {active ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setFilters({ type: null, key: null, q: "", barre: null })}
          >
            <X data-icon="inline-start" />
            Clear
          </Button>
        ) : null}
        <span className="ml-auto text-xs text-muted-foreground tabular-nums" aria-live="polite">
          {resultCount} {resultCount === 1 ? "chord" : "chords"}
        </span>
      </div>

      <ToggleGroup
        aria-label="Key"
        value={filters.key ? [filters.key] : []}
        onValueChange={(v) => setFilters({ key: (v[0] as typeof filters.key) ?? null })}
        size="sm"
        variant="outline"
        className="flex-wrap"
      >
        {CHORD_KEYS.map((k) => (
          <ToggleGroupItem
            key={k.id}
            value={k.id}
            aria-label={k.label}
            className="min-w-9 font-mono data-pressed:border-primary data-pressed:text-primary"
          >
            {k.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}
