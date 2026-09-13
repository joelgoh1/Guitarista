"use client";

import * as React from "react";
import { Guitar } from "lucide-react";
import {
  getAllChords,
  variationHasBarre,
  variationList,
  type FlatChord,
} from "@guitarista/music-theory";
import { EmptyState } from "@/components/common/EmptyState";
import { ChordCard } from "@/components/chords/ChordCard";
import { ChordFilters, useChordFilters } from "@/components/chords/ChordFilters";
import { keyFlatLabel, keyLabel, shortChordName } from "@/components/chords/labels";

function normalize(s: string) {
  return s.toLowerCase().replace(/♯/g, "#").replace(/♭/g, "b").replace(/\s+/g, " ").trim();
}

export function filterChords(
  chords: FlatChord[],
  f: { type?: string | null; key?: string | null; q?: string; barre?: string | null },
) {
  const q = normalize(f.q ?? "");
  return chords.filter((c) => {
    if (f.type && c.type !== f.type) return false;
    if (f.key && c.key !== f.key) return false;
    if (f.barre) {
      const has = variationList(c.entry).some(variationHasBarre);
      if ((f.barre === "yes") !== has) return false;
    }
    if (q) {
      const hay = [
        c.entry.name,
        shortChordName(c.type, c.key),
        keyLabel(c.key),
        keyFlatLabel(c.key) ?? "",
        c.type,
      ]
        .map(normalize)
        .join(" ");
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function ChordLibrary() {
  const [filters] = useChordFilters();
  const all = React.useMemo(() => getAllChords(), []);
  const visible = filterChords(all, filters);

  return (
    <div className="flex flex-col gap-6">
      <ChordFilters resultCount={visible.length} />
      {visible.length ? (
        <ul
          data-slot="chord-grid"
          className="grid list-none gap-4 p-0 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4"
        >
          {visible.map((c) => (
            <li key={`${c.type}-${c.key}`} className="contents">
              <ChordCard chord={c} />
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={Guitar}
          title="No chords match"
          description="Try a different key, type or search term."
        />
      )}
    </div>
  );
}
