"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useDropzone, type FileRejection } from "react-dropzone";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  FileMusic,
  Loader2,
  RotateCcw,
  Upload,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { TUNINGS, TUNING_LABELS, midiToNote } from "@guitarista/music-theory";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { healthQuery, useConvertScore, useUploadScore } from "@/lib/api/queries";
import { toApiError, type ApiError } from "@/lib/api/problem";
import type { CostProfile, OutOfRangePolicy, ScorePart, ScoreUploadResponse } from "@/lib/api/types";
import { formatBytes } from "@/components/song/AudioDropzone";
import { COST_PROFILE_ITEMS, TUNING_PRESETS, type TuningPreset } from "@/components/song/AdvancedOptions";
import { cn } from "@/lib/utils";

export const MAX_SCORE_BYTES = 10 * 1024 * 1024;

/** Formats the backend reads with music21 alone. */
const SCORE_ACCEPT = {
  "application/vnd.recordare.musicxml+xml": [".musicxml"],
  "application/vnd.recordare.musicxml": [".mxl"],
  "application/xml": [".xml"],
  "text/xml": [".xml"],
  "audio/midi": [".mid", ".midi"],
  "audio/x-midi": [".mid", ".midi"],
};

/**
 * Formats that need MuseScore on the API host. Only advertised when `/health` reports it,
 * so we never invite a file the server is going to reject.
 */
const MUSESCORE_ACCEPT = {
  "application/x-musescore": [".mscz", ".mscx"],
  "application/octet-stream": [".gp", ".gpx", ".gp3", ".gp4", ".gp5", ".cap", ".capx"],
};

export function scoreAccept(musescore: boolean | undefined) {
  return musescore ? { ...SCORE_ACCEPT, ...MUSESCORE_ACCEPT } : SCORE_ACCEPT;
}

export function acceptedScoreLabel(musescore: boolean | undefined) {
  return musescore
    ? "Only MusicXML, MIDI, MuseScore (.mscz) or Guitar Pro files are accepted."
    : "Only .musicxml, .xml, .mxl, .mid or .midi files are accepted.";
}

export interface ScoreOptions {
  tuning: TuningPreset;
  capo: number;
  maxFret: number;
  outOfRange: OutOfRangePolicy;
  costProfile: CostProfile;
}

const DEFAULT_OPTIONS: ScoreOptions = {
  tuning: "standard",
  capo: 0,
  maxFret: 19,
  outOfRange: "octave_shift",
  costProfile: "tabgen",
};

const POLICY_ITEMS: Array<{ value: OutOfRangePolicy; label: string; hint: string }> = [
  {
    value: "octave_shift",
    label: "Shift octave",
    hint: "Move unplayable notes by octaves until they fit.",
  },
  { value: "drop", label: "Drop notes", hint: "Silently remove notes outside the range." },
  { value: "raise", label: "Fail", hint: "Stop with an error if any note is out of range." },
];

const TUNING_ITEMS = TUNING_PRESETS.map((id) => ({ value: id, label: TUNING_LABELS[id] }));

export function ScoreUpload({ className }: { className?: string }) {
  const router = useRouter();
  const health = useQuery(healthQuery());
  const upload = useUploadScore();
  const convert = useConvertScore();
  const [uploaded, setUploaded] = React.useState<ScoreUploadResponse | null>(null);
  const [partIndex, setPartIndex] = React.useState<number>(0);
  const [options, setOptions] = React.useState<ScoreOptions>(DEFAULT_OPTIONS);
  const [convertError, setConvertError] = React.useState<ApiError | null>(null);

  const musescore = health.data?.features.musescore;

  const reset = () => {
    setUploaded(null);
    setPartIndex(0);
    setConvertError(null);
    convert.reset();
    upload.reset();
  };

  const onUpload = (file: File) => {
    setConvertError(null);
    upload.mutate(file, {
      onSuccess: (res) => {
        setUploaded(res);
        // Default to the part with the most notes.
        const best = [...res.parts].sort((a, b) => b.note_count - a.note_count)[0];
        setPartIndex(best?.index ?? 0);
      },
    });
  };

  const runConvert = (override?: Partial<ScoreOptions>) => {
    if (!uploaded) return;
    const opts = { ...options, ...override };
    if (override) setOptions(opts);
    setConvertError(null);
    convert.mutate(
      {
        upload_id: uploaded.upload_id,
        part_index: partIndex,
        tuning: opts.tuning === "standard" ? null : [...TUNINGS[opts.tuning]],
        capo: opts.capo,
        max_fret: opts.maxFret,
        out_of_range: opts.outOfRange,
        cost_profile: opts.costProfile,
      },
      {
        onSuccess: (tab) => {
          if (tab.id) router.push(`/tabs/${tab.id}`);
        },
        onError: (err) => setConvertError(toApiError(err, "Conversion failed")),
      },
    );
  };

  const busy = upload.isPending || convert.isPending;

  return (
    <div className={cn("flex max-w-2xl flex-col gap-4", className)}>
      <StepCard step={1} title="Upload a score" done={!!uploaded}>
        {uploaded ? (
          <div className="flex items-center gap-3">
            <span className="bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-lg">
              <FileMusic className="size-5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{uploaded.filename}</p>
              <p className="text-muted-foreground truncate text-xs">
                {[uploaded.artist, uploaded.title].filter(Boolean).join(" — ") || "No metadata"} ·{" "}
                {uploaded.parts.length} {uploaded.parts.length === 1 ? "part" : "parts"}
              </p>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={reset} disabled={busy}>
              <X data-icon="inline-start" /> Change
            </Button>
          </div>
        ) : (
          <ScoreDropzone onFile={onUpload} busy={upload.isPending} musescore={musescore} />
        )}
      </StepCard>

      <AnimatePresence initial={false}>
        {uploaded ? (
          <motion.div
            key="parts"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="flex flex-col gap-4"
          >
            <StepCard step={2} title="Pick the part to arrange">
              <PartsPicker
                parts={uploaded.parts}
                value={partIndex}
                onChange={setPartIndex}
                disabled={busy}
              />
            </StepCard>

            <StepCard step={3} title="Options">
              <ScoreOptionsForm value={options} onChange={setOptions} disabled={busy} />
            </StepCard>

            {convertError ? (
              <ConvertErrorCard
                error={convertError}
                options={options}
                onRetry={runConvert}
                busy={busy}
              />
            ) : null}

            <div className="flex justify-end">
              <Button
                type="button"
                onClick={() => runConvert()}
                disabled={busy || uploaded.parts.length === 0}
              >
                {convert.isPending ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : null}
                Convert to tab
                {!convert.isPending ? <ArrowRight data-icon="inline-end" /> : null}
              </Button>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function StepCard({
  step,
  title,
  done,
  children,
}: {
  step: number;
  title: string;
  done?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <span
            className={cn(
              "flex size-6 items-center justify-center rounded-full text-xs font-semibold",
              done ? "bg-success/15 text-success" : "bg-primary/10 text-primary",
            )}
          >
            {done ? <Check className="size-3.5" /> : step}
          </span>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function ScoreDropzone({
  onFile,
  busy,
  musescore,
}: {
  onFile: (f: File) => void;
  busy: boolean;
  musescore: boolean | undefined;
}) {
  const [error, setError] = React.useState<string | null>(null);
  const onDrop = React.useCallback(
    (accepted: File[], rejected: FileRejection[]) => {
      if (rejected.length) {
        const code = rejected[0]?.errors[0]?.code;
        setError(
          code === "file-too-large"
            ? `File is larger than ${formatBytes(MAX_SCORE_BYTES)}.`
            : acceptedScoreLabel(musescore),
        );
        return;
      }
      setError(null);
      if (accepted[0]) onFile(accepted[0]);
    },
    [onFile, musescore],
  );
  const accept = React.useMemo(() => scoreAccept(musescore), [musescore]);
  const { getRootProps, getInputProps, isDragActive, isDragReject, open } = useDropzone({
    onDrop,
    accept,
    maxSize: MAX_SCORE_BYTES,
    multiple: false,
    disabled: busy,
    noClick: true,
  });

  return (
    <div className="flex flex-col gap-2">
      <div
        {...getRootProps({
          className: cn(
            "flex min-h-36 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-muted/20 px-4 py-6 text-center text-sm transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
            isDragActive && !isDragReject && "border-primary bg-primary/5",
            isDragReject && "border-destructive bg-destructive/5",
            busy && "opacity-60",
          ),
          "aria-label": "Score file dropzone",
        })}
      >
        <input {...getInputProps()} data-testid="score-input" />
        <span className="bg-muted text-muted-foreground flex size-10 items-center justify-center rounded-full">
          {busy ? (
            <Loader2 className="size-5 animate-spin" aria-hidden />
          ) : (
            <Upload className="size-5" aria-hidden />
          )}
        </span>
        <p className="font-medium">
          {busy
            ? "Parsing score…"
            : isDragActive
              ? "Drop it here"
              : musescore
                ? "Drop a .musicxml, .mscz, Guitar Pro or .mid file"
                : "Drop a .musicxml, .mxl or .mid file"}
        </p>
        <p className="text-muted-foreground text-xs">
          up to {formatBytes(MAX_SCORE_BYTES)}
          {musescore ? null : " · install MuseScore Studio to also accept .mscz and Guitar Pro"}
        </p>
        {!busy ? (
          <Button type="button" variant="outline" size="sm" className="mt-1" onClick={open}>
            Choose file
          </Button>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function PartsPicker({
  parts,
  value,
  onChange,
  disabled,
}: {
  parts: ScorePart[];
  value: number;
  onChange: (index: number) => void;
  disabled?: boolean;
}) {
  if (parts.length === 0) {
    return <p className="text-muted-foreground text-sm">This score has no parts with notes.</p>;
  }
  return (
    <div role="radiogroup" aria-label="Score parts" className="grid gap-2 sm:grid-cols-2">
      {parts.map((part) => {
        const selected = part.index === value;
        return (
          <button
            key={part.index}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled || part.note_count === 0}
            onClick={() => onChange(part.index)}
            className={cn(
              "focus-visible:ring-ring/50 flex flex-col items-start gap-1 rounded-lg border px-3 py-2.5 text-left text-sm outline-none transition-colors focus-visible:ring-[3px] disabled:opacity-50",
              selected ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50",
            )}
          >
            <span className="flex w-full items-center justify-between gap-2">
              <span className="truncate font-medium">{part.name || `Part ${part.index + 1}`}</span>
              {selected ? <Check className="text-primary size-4 shrink-0" /> : null}
            </span>
            <span className="text-muted-foreground flex flex-wrap gap-x-3 text-xs">
              <span>{part.note_count} notes</span>
              {part.pitch_range ? (
                <span>
                  {midiToNote(part.pitch_range[0])} – {midiToNote(part.pitch_range[1])}
                </span>
              ) : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function ScoreOptionsForm({
  value,
  onChange,
  disabled,
}: {
  value: ScoreOptions;
  onChange: (v: ScoreOptions) => void;
  disabled?: boolean;
}) {
  const clampInt = (raw: string, min: number, max: number, fallback: number) => {
    const n = Number.parseInt(raw, 10);
    return Number.isNaN(n) ? fallback : Math.min(max, Math.max(min, n));
  };
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-2">
        <Label htmlFor="score-tuning">Tuning</Label>
        <Select
          items={TUNING_ITEMS}
          value={value.tuning}
          onValueChange={(v) => onChange({ ...value, tuning: v as TuningPreset })}
          disabled={disabled}
        >
          <SelectTrigger id="score-tuning" className="w-full">
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
        <Label htmlFor="score-policy">Out-of-range notes</Label>
        <Select
          items={POLICY_ITEMS}
          value={value.outOfRange}
          onValueChange={(v) => onChange({ ...value, outOfRange: v as OutOfRangePolicy })}
          disabled={disabled}
        >
          <SelectTrigger id="score-policy" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {POLICY_ITEMS.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-muted-foreground text-xs">
          {POLICY_ITEMS.find((p) => p.value === value.outOfRange)?.hint}
        </p>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="score-capo">Capo</Label>
        <Input
          id="score-capo"
          type="number"
          inputMode="numeric"
          min={0}
          max={12}
          value={value.capo}
          disabled={disabled}
          onChange={(e) => onChange({ ...value, capo: clampInt(e.target.value, 0, 12, 0) })}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="score-maxfret">Max fret</Label>
        <Input
          id="score-maxfret"
          type="number"
          inputMode="numeric"
          min={5}
          max={24}
          value={value.maxFret}
          disabled={disabled}
          onChange={(e) => onChange({ ...value, maxFret: clampInt(e.target.value, 5, 24, 19) })}
        />
      </div>
      <div className="flex flex-col gap-2 sm:col-span-2">
        <Label htmlFor="score-profile">Fretting style</Label>
        <Select
          items={COST_PROFILE_ITEMS}
          value={value.costProfile}
          onValueChange={(v) => onChange({ ...value, costProfile: v as CostProfile })}
          disabled={disabled}
        >
          <SelectTrigger id="score-profile" className="w-full">
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
        <p className="text-muted-foreground text-xs">
          {COST_PROFILE_ITEMS.find((p) => p.value === value.costProfile)?.hint}
        </p>
      </div>
    </div>
  );
}

function ConvertErrorCard({
  error,
  options,
  onRetry,
  busy,
}: {
  error: ApiError;
  options: ScoreOptions;
  onRetry: (override?: Partial<ScoreOptions>) => void;
  busy: boolean;
}) {
  const rangeProblem = error.status === 422 && /range|octave|fret|pitch/i.test(error.detail);
  const canOctaveShift = rangeProblem && options.outOfRange !== "octave_shift";
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="border-destructive/40" role="alert" data-testid="convert-error">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="text-destructive size-4" />
            {error.status === 422 ? "Couldn't arrange this part" : error.title}
            <Badge variant="destructive">{error.status || "network"}</Badge>
          </CardTitle>
          <CardDescription className="whitespace-pre-wrap">{error.detail}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {canOctaveShift ? (
            <Button
              type="button"
              size="sm"
              disabled={busy}
              onClick={() => onRetry({ outOfRange: "octave_shift" })}
            >
              <RotateCcw data-icon="inline-start" />
              Retry with octave shift
            </Button>
          ) : null}
          {rangeProblem && options.maxFret < 24 ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => onRetry({ maxFret: 24 })}
            >
              Retry with 24 frets
            </Button>
          ) : null}
          {!rangeProblem ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => onRetry()}
            >
              <RotateCcw data-icon="inline-start" />
              Retry
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </motion.div>
  );
}
