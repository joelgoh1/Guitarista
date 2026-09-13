import { describe, expect, it } from "vitest";
import { classifySongInput } from "@/components/song/spotify";

describe("classifySongInput", () => {
  it("recognises Spotify track URLs (with and without intl prefix / query)", () => {
    const id = "1qPbGZqppFwLwcBC1JQ6Vr";
    for (const url of [
      `https://open.spotify.com/track/${id}`,
      `https://open.spotify.com/intl-de/track/${id}?si=abc123`,
      `  open.spotify.com/track/${id}  `,
    ]) {
      const c = classifySongInput(url);
      expect(c.kind, url).toBe("spotify");
      if (c.kind === "spotify") expect(c.trackId).toBe(id);
    }
  });

  it("recognises spotify: URIs", () => {
    const c = classifySongInput("spotify:track:1qPbGZqppFwLwcBC1JQ6Vr");
    expect(c).toMatchObject({ kind: "spotify", trackId: "1qPbGZqppFwLwcBC1JQ6Vr" });
  });

  it("rejects non-track Spotify links with a hint", () => {
    const c = classifySongInput("https://open.spotify.com/album/2dIGnmEIy1WZIcZCFSj6i8");
    expect(c.kind).toBe("invalid");
    if (c.kind === "invalid") expect(c.reason).toMatch(/track/i);
  });

  it("treats plain text as a raw query", () => {
    expect(classifySongInput("Oasis - Wonderwall")).toEqual({ kind: "raw", raw: "Oasis - Wonderwall" });
    expect(classifySongInput("  wonderwall ")).toEqual({ kind: "raw", raw: "wonderwall" });
  });

  it("rejects empty input and other URLs", () => {
    expect(classifySongInput("   ").kind).toBe("invalid");
    expect(classifySongInput("https://www.youtube.com/watch?v=x").kind).toBe("invalid");
  });
});
