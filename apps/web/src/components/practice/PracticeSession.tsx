"use client";

import * as React from "react";
import { Play, Square, Timer } from "lucide-react";
import { getChord, variationList } from "@guitarista/music-theory";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Toggle } from "@/components/ui/toggle";
import { EmptyState } from "@/components/common/EmptyState";
import { ChordDiagram } from "@/components/chords/ChordDiagram";
import { ProgressionEditor } from "@/components/practice/ProgressionEditor";
import {
  DEFAULT_SESSION,
  loadSession,
  saveSession,
  type PracticeSessionState,
  type ProgressionStep,
} from "@/components/practice/types";
import { getAudioContext } from "@/lib/audio/context";
import { scheduleClick } from "@/lib/audio/metronome";

function stepVariation(s: ProgressionStep) {
  const entry = getChord(s.type, s.key);
  const vs = variationList(entry);
  return { entry, variation: vs[Math.min(s.variation, vs.length - 1)]! };
}

interface Playhead {
  step: number;
  /** 0-based beat within the current step. */
  beat: number;
}

export function PracticeSession() {
  // Rendered client-only (see PracticeSessionLoader), so localStorage is safe here.
  const [session, setSession] = React.useState<PracticeSessionState>(
    () => loadSession() ?? DEFAULT_SESSION,
  );
  const [running, setRunning] = React.useState(false);
  const [head, setHead] = React.useState<Playhead>({ step: 0, beat: 0 });

  React.useEffect(() => {
    saveSession(session);
  }, [session]);

  // Scheduler: look-ahead loop on the AudioContext clock.
  const sessionRef = React.useRef(session);
  React.useEffect(() => {
    sessionRef.current = session;
  }, [session]);
  React.useEffect(() => {
    if (!running) return;
    const ctx = getAudioContext();
    let step = 0;
    let beat = 0;
    let nextTime = ctx.currentTime + 0.1;
    const timer = window.setInterval(() => {
      const { steps, bpm, metronome } = sessionRef.current;
      if (!steps.length) return;
      const secPerBeat = 60 / bpm;
      while (nextTime < ctx.currentTime + 0.12) {
        if (metronome) scheduleClick(nextTime, beat === 0);
        const s = step;
        const b = beat;
        const delay = Math.max(0, (nextTime - ctx.currentTime) * 1000);
        window.setTimeout(() => setHead({ step: s, beat: b }), delay);
        beat++;
        if (beat >= (steps[step]?.beats ?? 4)) {
          beat = 0;
          step = (step + 1) % steps.length;
        }
        nextTime += secPerBeat;
      }
    }, 25);
    return () => window.clearInterval(timer);
  }, [running]);

  const steps = session.steps;
  const current = steps.length ? steps[Math.min(head.step, steps.length - 1)]! : null;
  const nextStep = steps.length ? steps[(Math.min(head.step, steps.length - 1) + 1) % steps.length]! : null;
  const beatsInStep = current?.beats ?? 4;
  const progress = running ? (head.beat + 1) / beatsInStep : 0;
  const R = 54;
  const circumference = 2 * Math.PI * R;

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <div className="flex flex-col gap-4">
        <Card>
          <CardContent className="flex flex-col items-center gap-6 py-6 sm:flex-row sm:justify-center sm:gap-12">
            {current ? (
              <>
                <div className="relative flex items-center justify-center" aria-live="polite">
                  <svg viewBox="0 0 120 120" className="absolute size-64" aria-hidden>
                    <circle cx={60} cy={60} r={R} fill="none" strokeWidth={3} className="stroke-muted" />
                    <circle
                      cx={60}
                      cy={60}
                      r={R}
                      fill="none"
                      strokeWidth={3}
                      strokeLinecap="round"
                      className="stroke-primary transition-[stroke-dashoffset] duration-150 ease-linear"
                      strokeDasharray={circumference}
                      strokeDashoffset={circumference * (1 - progress)}
                      transform="rotate(-90 60 60)"
                    />
                  </svg>
                  <div className="flex size-64 flex-col items-center justify-center gap-1">
                    <ChordDiagram
                      variation={stepVariation(current).variation}
                      size={150}
                      title={stepVariation(current).entry.name}
                    />
                    <p className="text-lg font-semibold">{stepVariation(current).entry.name}</p>
                    <p className="font-mono text-xs text-muted-foreground tabular-nums">
                      {running ? `beat ${head.beat + 1} / ${beatsInStep}` : `${beatsInStep} beats`}
                    </p>
                  </div>
                </div>
                {nextStep && steps.length > 1 ? (
                  <div className="flex flex-col items-center gap-1 text-muted-foreground">
                    <p className="text-xs uppercase tracking-wider">Next</p>
                    <ChordDiagram
                      variation={stepVariation(nextStep).variation}
                      size={80}
                      showFingers={false}
                      title={`Next: ${stepVariation(nextStep).entry.name}`}
                    />
                    <p className="text-sm font-medium">{stepVariation(nextStep).entry.name}</p>
                  </div>
                ) : null}
              </>
            ) : (
              <EmptyState title="No progression yet" description="Add chords below to build a loop." className="w-full" />
            )}
          </CardContent>
        </Card>

        <ProgressionEditor
          steps={steps}
          onChange={(s) => setSession((prev) => ({ ...prev, steps: s }))}
          activeIndex={running ? head.step : null}
          disabled={running}
        />
      </div>

      <Card className="h-fit">
        <CardHeader>
          <CardTitle>Session</CardTitle>
          <CardDescription>Tempo and metronome. The loop restarts from the first chord.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-sm">
              <label htmlFor="bpm">Tempo</label>
              <span className="font-mono tabular-nums">{session.bpm} BPM</span>
            </div>
            <Slider
              id="bpm"
              aria-label="Tempo"
              min={40}
              max={200}
              step={1}
              value={[session.bpm]}
              onValueChange={(v) => {
                const n = Array.isArray(v) ? v[0] : v;
                if (typeof n === "number") setSession((prev) => ({ ...prev, bpm: n }));
              }}
            />
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm">Metronome</span>
            <Toggle
              aria-label="Metronome"
              variant="outline"
              pressed={session.metronome}
              onPressedChange={(v) => setSession((prev) => ({ ...prev, metronome: v }))}
              className="data-pressed:text-primary"
            >
              <Timer />
            </Toggle>
          </div>
          <Button
            size="lg"
            variant={running ? "secondary" : "default"}
            disabled={!steps.length}
            onClick={() => {
              setHead({ step: 0, beat: 0 });
              setRunning((r) => !r);
            }}
          >
            {running ? <Square data-icon="inline-start" /> : <Play data-icon="inline-start" />}
            {running ? "Stop" : "Start"}
          </Button>
          <p className="text-xs text-muted-foreground">Your progression and tempo are saved in this browser.</p>
        </CardContent>
      </Card>
    </div>
  );
}
