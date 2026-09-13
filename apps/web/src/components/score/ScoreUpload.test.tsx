import { describe, expect, it } from "vitest";
import { acceptedScoreLabel, scoreAccept } from "./ScoreUpload";

describe("scoreAccept", () => {
  it("offers only music21-native formats when MuseScore is unavailable", () => {
    const exts = Object.values(scoreAccept(false)).flat();
    expect(exts).toContain(".musicxml");
    expect(exts).toContain(".mid");
    expect(exts).not.toContain(".mscz");
    expect(exts).not.toContain(".gp5");
  });

  it("adds MuseScore and Guitar Pro formats when the API reports MuseScore", () => {
    const exts = Object.values(scoreAccept(true)).flat();
    expect(exts).toEqual(expect.arrayContaining([".musicxml", ".mscz", ".mscx", ".gp5", ".gpx"]));
  });

  it("stays narrow while /health is still loading", () => {
    expect(Object.values(scoreAccept(undefined)).flat()).not.toContain(".mscz");
  });

  it("describes what is actually accepted", () => {
    expect(acceptedScoreLabel(true)).toContain(".mscz");
    expect(acceptedScoreLabel(false)).not.toContain(".mscz");
  });
});
