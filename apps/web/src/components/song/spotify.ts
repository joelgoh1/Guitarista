import { z } from "zod";

export const SPOTIFY_TRACK_RE =
  /(?:open\.spotify\.com\/(?:intl-[a-z]{2}\/)?track\/|spotify:track:)([A-Za-z0-9]{22})/i;

export const spotifyTrackSchema = z
  .string()
  .trim()
  .regex(SPOTIFY_TRACK_RE, "Not a Spotify track link");

export type SongInputClassification =
  | { kind: "spotify"; url: string; trackId: string }
  | { kind: "raw"; raw: string }
  | { kind: "invalid"; reason: string };

/**
 * Decide what the Link field holds: a Spotify track URL/URI, a non-track Spotify
 * link (rejected with a hint), or free text ("artist - title").
 */
export function classifySongInput(input: string): SongInputClassification {
  const text = input.trim();
  if (!text) return { kind: "invalid", reason: "Type a song or paste a Spotify link." };

  const parsed = spotifyTrackSchema.safeParse(text);
  if (parsed.success) {
    const trackId = SPOTIFY_TRACK_RE.exec(parsed.data)?.[1] ?? "";
    return { kind: "spotify", url: parsed.data, trackId };
  }

  if (/spotify\.com|^spotify:/i.test(text)) {
    return {
      kind: "invalid",
      reason: "Only Spotify track links are supported (open.spotify.com/track/… or spotify:track:…).",
    };
  }

  if (/^https?:\/\//i.test(text)) {
    return { kind: "invalid", reason: "Links from other sites aren't supported yet. Try \"Artist - Title\"." };
  }

  return { kind: "raw", raw: text };
}

export function spotifyTrackUrl(trackId: string): string {
  return `https://open.spotify.com/track/${trackId}`;
}
