"use client";

import * as React from "react";
import { ChevronDown, Settings2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { TUNINGS, TUNING_LABELS, type TuningId } from "@guitarista/music-theory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { CostProfile } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const TUNING_PRESETS = ["standard", "drop_d", "half_down", "dadgad"] as const satisfies readonly TuningId[];
export type TuningPreset = (typeof TUNING_PRESETS)[number];

export interface TabOptions {
  tuning: TuningPreset;
  capo: number;
  costProfile: CostProfile;
}

export const DEFAULT_TAB_OPTIONS: TabOptions = { tuning: "standard", capo: 0, costProfile: "tabgen" };

/** How the fretting solver should weigh its choices; mirrors `COST_PROFILES` in the API. */
export const COST_PROFILE_ITEMS: readonly { value: CostProfile; label: string; hint: string }[] = [
  { value: "tabgen", label: "Classic", hint: "Balanced heuristics; open strings are always welcome." },
  { value: "lead", label: "Lead (stay in position)", hint: "Keeps runs in one hand position instead of jumping to open strings." },
  { value: "beginner", label: "Beginner", hint: "Prefers open strings and the first few frets." },
];

export function costProfileLabel(profile: CostProfile): string {
  return COST_PROFILE_ITEMS.find((p) => p.value === profile)?.label ?? profile;
}

/** Convert UI options to the `tuning`/`capo`/`cost_profile` fields of a TabRequest. */
export function toRequestOptions(options: TabOptions): {
  tuning?: number[];
  capo: number;
  cost_profile: CostProfile;
} {
  return {
    tuning: options.tuning === "standard" ? undefined : [...TUNINGS[options.tuning]],
    capo: options.capo,
    cost_profile: options.costProfile,
  };
}

const TUNING_ITEMS = TUNING_PRESETS.map((id) => ({ value: id, label: TUNING_LABELS[id] }));

export interface AdvancedOptionsProps {
  value: TabOptions;
  onChange: (next: TabOptions) => void;
  className?: string;
  idPrefix?: string;
}

export function AdvancedOptions({ value, onChange, className, idPrefix = "opts" }: AdvancedOptionsProps) {
  const [open, setOpen] = React.useState(false);
  const isDefault = value.tuning === "standard" && value.capo === 0 && value.costProfile === "tabgen";

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="w-fit text-muted-foreground"
        aria-expanded={open}
        aria-controls={`${idPrefix}-panel`}
        onClick={() => setOpen((o) => !o)}
      >
        <Settings2 data-icon="inline-start" />
        Advanced options
        {!isDefault ? (
          <span className="text-xs text-primary">
            {[
              value.tuning !== "standard" ? TUNING_LABELS[value.tuning].split(" (")[0] : null,
              value.capo ? `capo ${value.capo}` : null,
              value.costProfile !== "tabgen" ? costProfileLabel(value.costProfile) : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        ) : null}
        <ChevronDown
          data-icon="inline-end"
          className={cn("transition-transform", open && "rotate-180")}
        />
      </Button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            id={`${idPrefix}-panel`}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="grid gap-4 rounded-lg border border-border bg-muted/30 p-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${idPrefix}-tuning`}>Tuning</Label>
                <Select
                  items={TUNING_ITEMS}
                  value={value.tuning}
                  onValueChange={(v) => onChange({ ...value, tuning: v as TuningPreset })}
                >
                  <SelectTrigger id={`${idPrefix}-tuning`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TUNING_ITEMS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${idPrefix}-capo`}>Capo</Label>
                <Input
                  id={`${idPrefix}-capo`}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={12}
                  value={value.capo}
                  onChange={(e) => {
                    const n = Number.parseInt(e.target.value, 10);
                    onChange({ ...value, capo: Number.isNaN(n) ? 0 : Math.min(12, Math.max(0, n)) });
                  }}
                />
              </div>
              <div className="flex flex-col gap-2 sm:col-span-2">
                <Label htmlFor={`${idPrefix}-profile`}>Fretting style</Label>
                <Select
                  items={COST_PROFILE_ITEMS}
                  value={value.costProfile}
                  onValueChange={(v) => onChange({ ...value, costProfile: v as CostProfile })}
                >
                  <SelectTrigger id={`${idPrefix}-profile`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {COST_PROFILE_ITEMS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {COST_PROFILE_ITEMS.find((p) => p.value === value.costProfile)?.hint}
                </p>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
