"use client";

import * as React from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { FileAudio, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const MAX_AUDIO_BYTES = 50 * 1024 * 1024;

export interface AudioDropzoneProps {
  file: File | null;
  onFile: (file: File | null) => void;
  disabled?: boolean;
  className?: string;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** react-dropzone wrapper for a single audio file (≤ 50 MB). */
export function AudioDropzone({ file, onFile, disabled, className }: AudioDropzoneProps) {
  const [error, setError] = React.useState<string | null>(null);

  const onDrop = React.useCallback(
    (accepted: File[], rejected: FileRejection[]) => {
      if (rejected.length) {
        const code = rejected[0]?.errors[0]?.code;
        setError(
          code === "file-too-large"
            ? `File is larger than ${formatBytes(MAX_AUDIO_BYTES)}.`
            : code === "file-invalid-type"
              ? "Only audio files are accepted (mp3, wav, m4a, flac, ogg)."
              : "That file can't be used.",
        );
        return;
      }
      setError(null);
      onFile(accepted[0] ?? null);
    },
    [onFile],
  );

  const { getRootProps, getInputProps, isDragActive, isDragReject, open } = useDropzone({
    onDrop,
    // Keep in sync with AUDIO_SUFFIXES in apps/api/.../api/uploads.py — anything else 422s.
    accept: { "audio/*": [".mp3", ".wav", ".m4a", ".flac", ".ogg"] },
    maxSize: MAX_AUDIO_BYTES,
    multiple: false,
    disabled,
    noClick: !!file,
  });

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div
        {...getRootProps({
          className: cn(
            "flex min-h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-muted/20 px-4 py-6 text-center text-sm transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
            isDragActive && !isDragReject && "border-primary bg-primary/5",
            isDragReject && "border-destructive bg-destructive/5",
            disabled && "cursor-not-allowed opacity-60",
            file && "cursor-default",
          ),
          "aria-label": "Audio file dropzone",
        })}
      >
        <input {...getInputProps()} data-testid="audio-input" />
        {file ? (
          <div className="flex w-full items-center gap-3 text-left">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileAudio className="size-5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{file.name}</p>
              <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Remove file"
              onClick={(e) => {
                e.stopPropagation();
                onFile(null);
              }}
            >
              <X />
            </Button>
          </div>
        ) : (
          <>
            <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <Upload className="size-5" aria-hidden />
            </span>
            <p className="font-medium">
              {isDragActive ? "Drop it here" : "Drag an audio file here, or click to browse"}
            </p>
            <p className="text-xs text-muted-foreground">
              mp3, wav, m4a, flac, ogg · up to {formatBytes(MAX_AUDIO_BYTES)}
            </p>
            {!disabled ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-1"
                onClick={(e) => {
                  e.stopPropagation();
                  open();
                }}
              >
                Choose file
              </Button>
            ) : null}
          </>
        )}
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
