"use client";

import * as React from "react";
import { Loader2, Play, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChordSampler } from "@/hooks/useChordSampler";
import type { StrumOptions } from "@/lib/audio/chordSampler";

export interface ChordPlayButtonProps extends Omit<React.ComponentProps<typeof Button>, "onClick"> {
  midiNotes: readonly number[];
  mode?: "strum" | "block";
  strumOptions?: StrumOptions;
  label?: string;
  children?: React.ReactNode;
}

/** Plays a voicing through the shared smplr sampler; shows a spinner while the soundfont loads. */
export function ChordPlayButton({
  midiNotes,
  mode = "strum",
  strumOptions,
  label,
  children,
  ...props
}: ChordPlayButtonProps) {
  const { loading, play, playBlock, error } = useChordSampler();
  const [pending, setPending] = React.useState(false);
  const busy = pending && loading;

  const onClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setPending(true);
    try {
      if (mode === "block") await playBlock(midiNotes);
      else await play(midiNotes, strumOptions);
    } finally {
      setPending(false);
    }
  };

  const text = label ?? (mode === "block" ? "Play block" : "Strum");
  return (
    <Button
      type="button"
      aria-label={text}
      title={error ? `Audio failed to load: ${error}` : text}
      onClick={onClick}
      {...props}
    >
      {busy ? (
        <Loader2 className="animate-spin" data-icon={children ? "inline-start" : undefined} />
      ) : mode === "block" ? (
        <Square data-icon={children ? "inline-start" : undefined} />
      ) : (
        <Play data-icon={children ? "inline-start" : undefined} />
      )}
      {children}
    </Button>
  );
}
