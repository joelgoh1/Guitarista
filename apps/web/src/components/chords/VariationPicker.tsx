"use client";

import * as React from "react";
import type { ChordVariation } from "@guitarista/music-theory";
import { variationBaseFret, variationHasBarre } from "@guitarista/music-theory";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export interface VariationPickerProps {
  variations: ChordVariation[];
  value: number;
  onChange: (index: number) => void;
}

/** Tab strip selecting a voicing by index (0-based). */
export function VariationPicker({ variations, value, onChange }: VariationPickerProps) {
  return (
    <Tabs value={value} onValueChange={(v) => typeof v === "number" && onChange(v)}>
      <TabsList aria-label="Voicing">
        {variations.map((v, i) => {
          const base = variationBaseFret(v);
          return (
            <TabsTrigger key={i} value={i} className="gap-1.5 px-3">
              <span>Voicing {i + 1}</span>
              <span className="font-mono text-[11px] text-muted-foreground">
                {base <= 1 ? "open" : `${base}fr`}
                {variationHasBarre(v) ? " · barre" : ""}
              </span>
            </TabsTrigger>
          );
        })}
      </TabsList>
    </Tabs>
  );
}
