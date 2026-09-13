"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Music2, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { spotifySearchQuery } from "@/lib/api/queries";
import type { Song } from "@/lib/api/types";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { cn } from "@/lib/utils";

export interface SongSearchProps {
  /** Spotify credentials configured on the backend. */
  spotifyEnabled: boolean;
  onPick: (song: Song) => void;
  /** Fallback when Spotify is off: submit the typed text as a raw query. */
  onSubmitRaw: (raw: string) => void;
  busy?: boolean;
}

export function SongSearch({ spotifyEnabled, onPick, onSubmitRaw, busy }: SongSearchProps) {
  const [text, setText] = React.useState("");
  const q = useDebouncedValue(text.trim(), 300);
  const search = useQuery({ ...spotifySearchQuery(q), enabled: spotifyEnabled && q.length >= 2 });
  const disabledByHeader = search.data?.disabled === true;
  const effectiveEnabled = spotifyEnabled && !disabledByHeader;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim()) onSubmitRaw(text.trim());
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          aria-label="Search songs"
          placeholder={effectiveEnabled ? "Search Spotify… e.g. Wonderwall" : "Type artist and title…"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="pl-8"
          autoComplete="off"
          disabled={busy}
        />
        {search.isFetching ? (
          <Loader2 className="absolute top-1/2 right-2.5 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
        ) : null}
      </div>

      {!effectiveEnabled ? (
        <p className="text-xs text-muted-foreground">
          Spotify search is off (no <code className="font-mono">GUITARISTA_SPOTIFY_CLIENT_ID</code> on the
          API). Press Enter to search tab sources with the text as-is.
        </p>
      ) : null}

      {effectiveEnabled && q.length >= 2 ? (
        <ul className="flex flex-col divide-y divide-border overflow-hidden rounded-lg border border-border" aria-label="Search results">
          {search.isPending && !search.data
            ? Array.from({ length: 3 }).map((_, i) => (
                <li key={i} className="flex items-center gap-3 p-2">
                  <Skeleton className="size-10 rounded-md" />
                  <div className="flex flex-1 flex-col gap-1.5">
                    <Skeleton className="h-3.5 w-1/2" />
                    <Skeleton className="h-3 w-1/3" />
                  </div>
                </li>
              ))
            : null}
          {search.data && search.data.songs.length === 0 ? (
            <li className="p-3 text-sm text-muted-foreground">
              No Spotify matches. Press Enter to try tab sources with &ldquo;{q}&rdquo;.
            </li>
          ) : null}
          {search.data?.songs.map((song) => (
            <li key={song.id}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onPick(song)}
                className={cn(
                  "flex w-full items-center gap-3 p-2 text-left transition-colors outline-none hover:bg-muted/60 focus-visible:bg-muted/60 disabled:opacity-60",
                )}
              >
                {song.artwork_url ? (
                  // eslint-disable-next-line @next/next/no-img-element -- remote art from Spotify CDN, unknown hosts
                  <img
                    src={song.artwork_url}
                    alt=""
                    width={40}
                    height={40}
                    className="size-10 shrink-0 rounded-md object-cover"
                  />
                ) : (
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                    <Music2 className="size-4" aria-hidden />
                  </span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{song.title}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {song.artist}
                    {song.album ? ` · ${song.album}` : ""}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </form>
  );
}
