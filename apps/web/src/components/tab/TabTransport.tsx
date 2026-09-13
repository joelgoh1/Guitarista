"use client";

import * as React from "react";
import {
  Gauge,
  Guitar,
  Layers,
  Loader2,
  Pause,
  Play,
  Repeat,
  Square,
  Timer,
  Volume2,
  VolumeX,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Toggle } from "@/components/ui/toggle";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { usePlayerApi } from "@/lib/alphatab/context";
import { usePlayerStore, type StaveProfile } from "@/lib/stores/player";
import * as controls from "@/lib/alphatab/controls";
import { TrackSheet } from "@/components/tab/TrackSheet";

function formatTime(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function isTypingTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable
  );
}

export interface TabTransportProps {
  className?: string;
}

/** Docked playback controls. Drives the AlphaTabApi from PlayerApiProvider. */
export function TabTransport({ className }: TabTransportProps) {
  const api = usePlayerApi();
  const state = usePlayerStore((s) => s.state);
  const soundFontLoaded = usePlayerStore((s) => s.soundFontLoaded);
  const positionMs = usePlayerStore((s) => s.positionMs);
  const durationMs = usePlayerStore((s) => s.durationMs);
  const speed = usePlayerStore((s) => s.speed);
  const loop = usePlayerStore((s) => s.loop);
  const masterVolume = usePlayerStore((s) => s.masterVolume);
  const metronome = usePlayerStore((s) => s.metronome);
  const capoOn = usePlayerStore((s) => s.capoOn);
  const capoFret = usePlayerStore((s) => s.tracks.find((t) => t.capo > 0)?.capo ?? 0);
  const staveProfile = usePlayerStore((s) => s.staveProfile);
  const {
    setSpeed,
    setLoop,
    setMasterVolume,
    setMetronome,
    setCapoOn,
    setStaveProfile,
  } = usePlayerStore.getState();

  const isPlaying = state === "playing";
  const canPlay = !!api && soundFontLoaded && state !== "loading" && state !== "error";

  const playPause = React.useCallback(() => {
    if (!api) return;
    api.playPause();
  }, [api]);

  const stop = React.useCallback(() => {
    api?.stop();
  }, [api]);

  // Space toggles playback unless the user is typing.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || isTypingTarget(e.target)) return;
      if (e.target instanceof HTMLButtonElement) return; // let buttons handle their own space
      e.preventDefault();
      playPause();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [playPause]);

  const onSpeed = (value: number | readonly number[]) => {
    const v = Array.isArray(value) ? value[0] : value;
    if (typeof v !== "number" || !api) return;
    controls.setPlaybackSpeed(api, v / 100);
    setSpeed(v / 100);
  };

  const onVolume = (value: number | readonly number[]) => {
    const v = Array.isArray(value) ? value[0] : value;
    if (typeof v !== "number" || !api) return;
    controls.setMasterVolume(api, v / 100);
    setMasterVolume(v / 100);
  };

  const onLoop = (next: boolean) => {
    if (!api) return;
    controls.setLooping(api, next);
    setLoop(next);
  };

  const onMetronome = (next: boolean) => {
    if (!api) return;
    controls.setMetronome(api, next);
    setMetronome(next);
  };

  const onCapo = (next: boolean) => {
    if (!api) return;
    controls.applyCapoPlayback(api, next);
    setCapoOn(next);
  };

  const onStaveProfile = (next: StaveProfile) => {
    if (!api) return;
    controls.setStaveProfile(api, next);
    setStaveProfile(next);
  };

  return (
    <div
      data-slot="tab-transport"
      role="toolbar"
      aria-label="Playback"
      className={cn(
        "flex flex-wrap items-center gap-2 border-t border-border bg-card/80 px-3 py-2 backdrop-blur supports-backdrop-filter:bg-card/70 sm:gap-3 sm:px-4",
        className,
      )}
    >
      <div className="flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                size="icon"
                variant="default"
                aria-label={isPlaying ? "Pause" : "Play"}
                disabled={!canPlay}
                onClick={playPause}
              />
            }
          >
            {state === "loading" || (!soundFontLoaded && state !== "error") ? (
              <Loader2 className="animate-spin" />
            ) : isPlaying ? (
              <Pause />
            ) : (
              <Play />
            )}
          </TooltipTrigger>
          <TooltipContent>{isPlaying ? "Pause" : "Play"} (Space)</TooltipContent>
        </Tooltip>
        <Button size="icon" variant="ghost" aria-label="Stop" disabled={!api} onClick={stop}>
          <Square />
        </Button>
      </div>

      <div className="font-mono text-xs text-muted-foreground tabular-nums">
        <span className="text-foreground">{formatTime(positionMs)}</span>
        <span className="px-1">/</span>
        <span>{formatTime(durationMs)}</span>
      </div>

      <Separator orientation="vertical" className="hidden h-6 sm:block" />

      <div className="flex min-w-40 flex-1 items-center gap-2 sm:max-w-56">
        <Gauge className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <Slider
          aria-label="Tempo"
          min={50}
          max={150}
          step={5}
          value={[Math.round(speed * 100)]}
          onValueChange={onSpeed}
          disabled={!api}
        />
        <span className="w-10 text-right font-mono text-xs tabular-nums text-muted-foreground">
          {Math.round(speed * 100)}%
        </span>
      </div>

      <div className="flex items-center gap-1">
        <Toggle
          aria-label="Loop"
          pressed={loop}
          onPressedChange={onLoop}
          disabled={!api}
          className="data-pressed:text-primary"
        >
          <Repeat />
        </Toggle>
        <Toggle
          aria-label="Metronome"
          pressed={metronome}
          onPressedChange={onMetronome}
          disabled={!api}
          className="data-pressed:text-primary"
        >
          <Timer />
        </Toggle>
        {capoFret > 0 ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <Toggle
                  aria-label={capoOn ? `Capo on (fret ${capoFret})` : "Capo off"}
                  pressed={capoOn}
                  onPressedChange={onCapo}
                  disabled={!api}
                  className="data-pressed:text-primary"
                />
              }
            >
              <Guitar />
              <span className="font-mono text-xs tabular-nums">Capo {capoFret}</span>
            </TooltipTrigger>
            <TooltipContent>
              {capoOn
                ? "Play as written with the capo"
                : `Play as if the capo were removed (same frets, ${capoFret} semitones lower)`}
            </TooltipContent>
          </Tooltip>
        ) : null}
        <Toggle
          aria-label={staveProfile === "tab" ? "Show notation and tab" : "Show tab only"}
          pressed={staveProfile === "scoreTab"}
          onPressedChange={(v) => onStaveProfile(v ? "scoreTab" : "tab")}
          disabled={!api}
          className="data-pressed:text-primary"
        >
          <Layers />
        </Toggle>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <div className="hidden items-center gap-2 md:flex">
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label={masterVolume === 0 ? "Unmute" : "Mute"}
            onClick={() => onVolume(masterVolume === 0 ? 100 : 0)}
            disabled={!api}
          >
            {masterVolume === 0 ? <VolumeX /> : <Volume2 />}
          </Button>
          <Slider
            aria-label="Master volume"
            className="w-24"
            min={0}
            max={100}
            step={1}
            value={[Math.round(masterVolume * 100)]}
            onValueChange={onVolume}
            disabled={!api}
          />
        </div>
        <TrackSheet />
      </div>
    </div>
  );
}
