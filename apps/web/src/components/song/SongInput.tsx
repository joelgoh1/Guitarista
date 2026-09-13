"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import { ArrowRight, Link2, Loader2, Search, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { healthQuery, useCreateJob, useUploadAudio } from "@/lib/api/queries";
import type { CreateJobRequest, Song } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { AdvancedOptions, DEFAULT_TAB_OPTIONS, toRequestOptions, type TabOptions } from "./AdvancedOptions";
import { AudioDropzone } from "./AudioDropzone";
import { SongSearch } from "./SongSearch";
import { classifySongInput, spotifyTrackUrl } from "./spotify";

const INPUT_TABS = ["link", "search", "upload"] as const;
export type SongInputTab = (typeof INPUT_TABS)[number];
const tabParser = parseAsStringLiteral(INPUT_TABS).withDefault("link");

export function SongInput({ className }: { className?: string }) {
  const router = useRouter();
  const [tab, setTab] = useQueryState("tab", tabParser);
  const [options, setOptions] = React.useState<TabOptions>(DEFAULT_TAB_OPTIONS);
  const health = useQuery(healthQuery());
  const createJob = useCreateJob();
  const uploadAudio = useUploadAudio();

  const features = health.data?.features;
  const busy = createJob.isPending || uploadAudio.isPending;

  const submitRequest = React.useCallback(
    (partial: Omit<CreateJobRequest, "capo" | "tuning" | "cost_profile">) => {
      createJob.mutate(
        { ...partial, ...toRequestOptions(options) },
        { onSuccess: (job) => router.push(`/songs/${job.id}`) },
      );
    },
    [createJob, options, router],
  );

  // ---- Link / raw text ----
  const [linkText, setLinkText] = React.useState("");
  const [linkError, setLinkError] = React.useState<string | null>(null);
  const classification = React.useMemo(() => classifySongInput(linkText), [linkText]);

  const submitLink = (e: React.FormEvent) => {
    e.preventDefault();
    const c = classifySongInput(linkText);
    if (c.kind === "invalid") {
      setLinkError(c.reason);
      return;
    }
    setLinkError(null);
    submitRequest({ song: c.kind === "spotify" ? { spotify_url: c.url } : { raw: c.raw } });
  };

  // ---- Search ----
  const pickSong = (song: Song) => {
    submitRequest({
      song: {
        title: song.title,
        artist: song.artist,
        spotify_url: song.spotify_id ? spotifyTrackUrl(song.spotify_id) : undefined,
      },
    });
  };

  // ---- Upload ----
  const [file, setFile] = React.useState<File | null>(null);
  const [audioUrl, setAudioUrl] = React.useState("");
  const [uploadTitle, setUploadTitle] = React.useState("");
  const [uploadArtist, setUploadArtist] = React.useState("");
  const audioEnabled = features?.audio !== false;
  const ytdlpEnabled = features?.ytdlp === true;
  const trimmedUrl = audioUrl.trim();
  const urlValid = /^https?:\/\/\S+$/i.test(trimmedUrl);

  const submitUpload = (e: React.FormEvent) => {
    e.preventDefault();
    const title = uploadTitle.trim();
    const artist = uploadArtist.trim();
    const song = title || artist ? { title: title || undefined, artist: artist || undefined } : undefined;
    // A file always wins over a URL — it needs no download and the server prefers it too.
    if (file) {
      uploadAudio.mutate(file, {
        onSuccess: (res) => submitRequest({ upload_id: res.upload_id, song, tiers: ["audio"] }),
      });
      return;
    }
    if (urlValid) submitRequest({ audio_url: trimmedUrl, song, tiers: ["audio"] });
  };

  return (
    <Card className={cn("max-w-2xl", className)}>
      <CardHeader>
        <CardTitle>New tab request</CardTitle>
        <CardDescription>Choose how to identify the song.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <Tabs value={tab} onValueChange={(v) => void setTab(v as SongInputTab)}>
          <TabsList>
            <TabsTrigger value="link">
              <Link2 data-icon="inline-start" /> Link
            </TabsTrigger>
            <TabsTrigger value="search">
              <Search data-icon="inline-start" /> Search
            </TabsTrigger>
            <TabsTrigger value="upload">
              <Upload data-icon="inline-start" /> Upload
            </TabsTrigger>
          </TabsList>

          <TabsContent value="link" className="pt-4">
            <form onSubmit={submitLink} className="flex flex-col gap-3">
              <Label htmlFor="song-link" className="sr-only">
                Spotify link or song text
              </Label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  id="song-link"
                  name="song"
                  placeholder="Spotify track link, or “Oasis - Wonderwall”"
                  value={linkText}
                  onChange={(e) => {
                    setLinkText(e.target.value);
                    if (linkError) setLinkError(null);
                  }}
                  aria-invalid={!!linkError}
                  aria-describedby="song-link-hint"
                  autoComplete="off"
                  autoFocus
                  disabled={busy}
                />
                <Button type="submit" disabled={busy || !linkText.trim()} className="sm:w-auto">
                  {busy ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}
                  Find tab
                  {!busy ? <ArrowRight data-icon="inline-end" /> : null}
                </Button>
              </div>
              <p id="song-link-hint" className={cn("text-xs", linkError ? "text-destructive" : "text-muted-foreground")} role={linkError ? "alert" : undefined}>
                {linkError
                  ? linkError
                  : classification.kind === "spotify"
                    ? `Spotify track ${classification.trackId}${features && !features.spotify ? " — Spotify is not configured on the API; resolution will fall back to text." : ""}`
                    : classification.kind === "raw"
                      ? `Searching tab sources for “${classification.raw}”`
                      : "Paste an open.spotify.com/track link or type artist and title."}
              </p>
            </form>
          </TabsContent>

          <TabsContent value="search" className="pt-4">
            <SongSearch
              spotifyEnabled={features?.spotify === true}
              onPick={pickSong}
              onSubmitRaw={(raw) => submitRequest({ song: { raw } })}
              busy={busy}
            />
          </TabsContent>

          <TabsContent value="upload" className="pt-4">
            <form onSubmit={submitUpload} className="flex flex-col gap-4">
              {!audioEnabled ? (
                <p className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-xs text-foreground">
                  The audio tier is disabled on the API (<code className="font-mono">GUITARISTA_ENABLE_AUDIO_TIER=false</code>).
                  Uploads will be accepted but no transcription can run.
                </p>
              ) : features && !features.ml_sidecar_ok ? (
                <p className="text-xs text-muted-foreground">
                  The ML sidecar hasn&apos;t been probed as ready yet; transcription may fail until{" "}
                  <code className="font-mono">apps/ml</code> is synced.
                </p>
              ) : null}
              <AudioDropzone file={file} onFile={setFile} disabled={busy} />
              {ytdlpEnabled ? (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="audio-url">…or paste a YouTube URL</Label>
                  <Input
                    id="audio-url"
                    type="url"
                    inputMode="url"
                    placeholder="https://www.youtube.com/watch?v=…"
                    value={audioUrl}
                    onChange={(e) => setAudioUrl(e.target.value)}
                    aria-invalid={trimmedUrl.length > 0 && !urlValid}
                    aria-describedby="audio-url-hint"
                    autoComplete="off"
                    disabled={busy || !!file}
                  />
                  <p id="audio-url-hint" className="text-xs text-muted-foreground">
                    {file
                      ? "Remove the file above to transcribe from a URL instead."
                      : trimmedUrl && !urlValid
                        ? "Enter a full http(s) link."
                        : "Use this when the automatic match picks the wrong recording."}
                  </p>
                </div>
              ) : null}
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="upload-title">Title (optional)</Label>
                  <Input id="upload-title" value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} disabled={busy} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="upload-artist">Artist (optional)</Label>
                  <Input id="upload-artist" value={uploadArtist} onChange={(e) => setUploadArtist(e.target.value)} disabled={busy} />
                </div>
              </div>
              <Button type="submit" disabled={busy || (!file && !urlValid)} className="w-fit">
                {busy ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Upload data-icon="inline-start" />}
                {uploadAudio.isPending ? "Uploading…" : !file && urlValid ? "Fetch & transcribe" : "Upload & transcribe"}
              </Button>
            </form>
          </TabsContent>
        </Tabs>

        <AdvancedOptions value={options} onChange={setOptions} />

        {health.isError ? (
          <p className="text-xs text-destructive">
            Can&apos;t reach the API at the configured <code className="font-mono">NEXT_PUBLIC_API_URL</code>. Start it with{" "}
            <code className="font-mono">pnpm --filter @guitarista/api dev</code>.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
