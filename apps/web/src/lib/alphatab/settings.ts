import type * as alphaTab from "@coderline/alphatab";
import { env } from "@/lib/env";
import { readTokenRgba, type Rgba } from "@/lib/alphatab/colors";
import { ALPHATAB_FONT_DIR, ALPHATAB_SCRIPT, ALPHATAB_SOUNDFONT } from "@/lib/alphatab/paths";
import type { AlphaTabModule } from "@/lib/alphatab/loader";
import type { StaveProfile } from "@/lib/stores/player";

export interface BuildSettingsOptions {
  scrollElement: HTMLElement | string;
  staveProfile?: StaveProfile;
  /** Override worker usage; defaults to env NEXT_PUBLIC_ALPHATAB_WORKERS. */
  useWorkers?: boolean;
}

const LIGHT: Rgba = { r: 240, g: 240, b: 240, a: 255 };
const DIM: Rgba = { r: 140, g: 140, b: 140, a: 255 };

export function toAlphaTabStaveProfile(
  at: AlphaTabModule,
  profile: StaveProfile,
): alphaTab.StaveProfile {
  return profile === "scoreTab" ? at.StaveProfile.ScoreTab : at.StaveProfile.Tab;
}

/**
 * Rhythm notation under the tab staff.
 *
 * alphaTab's `Automatic` mode only looks at the staff's own
 * `showStandardNotation` flag, which our alphaTex leaves on, so a tab-only
 * profile would render no rhythm at all. Show it explicitly when the score
 * staff is hidden; the score staff carries the rhythm otherwise.
 *
 * We only want the *tuplet* brackets ("3" under triplet groups), not the
 * stems/flags/beams -- but alphaTab only paints tuplets on a tab staff when
 * the rhythm mode is not `Hidden` (`TabBarRenderer.paintTuplets`). So the
 * rhythm stays on and the stems/flags/beams are painted fully transparent per
 * beat; see `applyTabRhythmBeatStyles`. `ShowWithBars` groups beams instead of
 * giving every note its own flag, which keeps the (invisible) layout compact.
 */
export function toAlphaTabRhythmMode(
  at: AlphaTabModule,
  profile: StaveProfile,
): alphaTab.TabRhythmMode {
  return profile === "scoreTab" ? at.TabRhythmMode.Hidden : at.TabRhythmMode.ShowWithBars;
}

/**
 * Stem length under the tab staff (Songsterr-like: stems joined by beams for
 * quavers, plain stems for crotchets, tuplet brackets under the beams).
 * alphaTab's default is 25.
 */
export const TAB_RHYTHM_HEIGHT = 15;

/**
 * Thin, Songsterr-like engraving for the rhythm under the tab. Values are px
 * at display scale 1 (alphaTab's staff space is 9px; Bravura defaults are
 * stem 1.08px, beam 4.5px). Copied once from the font at startup, so
 * overriding them here is stable across renders.
 */
export function applyEngraving(settings: alphaTab.Settings) {
  const e = settings.display.resources.engravingSettings;
  e.stemThickness = 0.9;
  e.beamThickness = 1.8;
  e.beamSpacing = 2.2;
  e.tupletBracketThickness = 0.9;
}

/** Apply the current theme's tokens onto alphaTab's rendering resources. */
export function applyThemeColors(at: AlphaTabModule, settings: alphaTab.Settings) {
  const toColor = (rgba: Rgba) => new at.model.Color(rgba.r, rgba.g, rgba.b, rgba.a);
  const glyph = toColor(readTokenRgba("--tab-glyph", LIGHT));
  const secondary = toColor(readTokenRgba("--tab-glyph-secondary", DIM));
  const staff = toColor(readTokenRgba("--tab-staff-line", DIM));
  const r = settings.display.resources;
  r.mainGlyphColor = glyph;
  r.secondaryGlyphColor = secondary;
  r.scoreInfoColor = glyph;
  r.barNumberColor = secondary;
  r.staffLineColor = staff;
  r.barSeparatorColor = staff;
}

/**
 * Build alphaTab settings for the browser. `core.scriptFile` is absolute so
 * the worker/worklet fallbacks inside alphaTab can resolve it; the primary
 * path resolves siblings of the runtime module via `import.meta.url`.
 */
export function buildSettings(at: AlphaTabModule, opts: BuildSettingsOptions): alphaTab.Settings {
  const useWorkers = opts.useWorkers ?? env.NEXT_PUBLIC_ALPHATAB_WORKERS !== "false";
  const origin = typeof window !== "undefined" ? window.location.origin : "";

  const settings = new at.Settings();

  settings.core.scriptFile = `${origin}${ALPHATAB_SCRIPT}`;
  settings.core.fontDirectory = ALPHATAB_FONT_DIR;
  settings.core.engine = "svg";
  settings.core.useWorkers = useWorkers;
  settings.core.logLevel = at.LogLevel.Warning;

  settings.player.enablePlayer = true;
  settings.player.enableCursor = true;
  settings.player.enableUserInteraction = true;
  settings.player.soundFont = ALPHATAB_SOUNDFONT;
  settings.player.scrollElement = opts.scrollElement;
  settings.player.scrollMode = at.ScrollMode.Continuous;
  settings.player.scrollOffsetY = -48;
  // Without workers the AudioWorklet module cannot be used either; fall back
  // to the (deprecated but universally supported) ScriptProcessor output.
  settings.player.outputMode = useWorkers
    ? at.PlayerOutputMode.WebAudioAudioWorklets
    : at.PlayerOutputMode.WebAudioScriptProcessor;

  settings.display.staveProfile = toAlphaTabStaveProfile(at, opts.staveProfile ?? "tab");
  settings.notation.rhythmMode = toAlphaTabRhythmMode(at, opts.staveProfile ?? "tab");
  settings.notation.rhythmHeight = TAB_RHYTHM_HEIGHT;
  settings.display.scale = 1;
  settings.display.layoutMode = at.LayoutMode.Page;
  applyThemeColors(at, settings);
  applyEngraving(settings);

  return settings;
}
