"use client";

import * as React from "react";
import { Eye, EyeOff, Headphones, ListMusic, VolumeX } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Toggle } from "@/components/ui/toggle";
import { Separator } from "@/components/ui/separator";
import { usePlayerApi } from "@/lib/alphatab/context";
import { usePlayerStore } from "@/lib/stores/player";

/** Per-track mute / solo / visibility controls. */
export function TrackSheet() {
  const api = usePlayerApi();
  const tracks = usePlayerStore((s) => s.tracks);
  const updateTrack = usePlayerStore((s) => s.updateTrack);

  const withTrack = (index: number) => api?.score?.tracks.find((t) => t.index === index);

  const toggleMute = (index: number, next: boolean) => {
    const t = withTrack(index);
    if (!api || !t) return;
    api.changeTrackMute([t], next);
    updateTrack(index, { isMute: next });
  };

  const toggleSolo = (index: number, next: boolean) => {
    const t = withTrack(index);
    if (!api || !t) return;
    api.changeTrackSolo([t], next);
    updateTrack(index, { isSolo: next });
  };

  const toggleVisible = (index: number, next: boolean) => {
    if (!api?.score) return;
    const visible = new Set(tracks.filter((t) => t.visible).map((t) => t.index));
    if (next) visible.add(index);
    else visible.delete(index);
    if (visible.size === 0) return; // always render at least one track
    api.renderTracks(api.score.tracks.filter((t) => visible.has(t.index)));
    updateTrack(index, { visible: next });
  };

  return (
    <Sheet>
      <SheetTrigger
        render={<Button variant="ghost" size="sm" aria-label="Tracks" />}
        disabled={tracks.length === 0}
      >
        <ListMusic />
        <span className="hidden sm:inline">Tracks</span>
      </SheetTrigger>
      <SheetContent side="right" className="w-full max-w-sm">
        <SheetHeader>
          <SheetTitle>Tracks</SheetTitle>
          <SheetDescription>Choose what you hear and what you see.</SheetDescription>
        </SheetHeader>
        <Separator />
        <ul className="flex flex-col gap-1 p-4">
          {tracks.map((t) => (
            <li
              key={t.index}
              className="flex items-center justify-between gap-3 rounded-md px-2 py-2 hover:bg-muted/60"
            >
              <span className="truncate text-sm font-medium">{t.name}</span>
              <div className="flex shrink-0 items-center gap-1">
                <Toggle
                  size="sm"
                  aria-label={`Mute ${t.name}`}
                  pressed={t.isMute}
                  onPressedChange={(v) => toggleMute(t.index, v)}
                  className="data-pressed:text-destructive"
                >
                  <VolumeX />
                </Toggle>
                <Toggle
                  size="sm"
                  aria-label={`Solo ${t.name}`}
                  pressed={t.isSolo}
                  onPressedChange={(v) => toggleSolo(t.index, v)}
                  className="data-pressed:text-primary"
                >
                  <Headphones />
                </Toggle>
                <Toggle
                  size="sm"
                  aria-label={`${t.visible ? "Hide" : "Show"} ${t.name}`}
                  pressed={t.visible}
                  onPressedChange={(v) => toggleVisible(t.index, v)}
                >
                  {t.visible ? <Eye /> : <EyeOff />}
                </Toggle>
              </div>
            </li>
          ))}
        </ul>
      </SheetContent>
    </Sheet>
  );
}
