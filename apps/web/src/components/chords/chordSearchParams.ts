import { CHORD_KEY_IDS, CHORD_TYPE_IDS } from "@guitarista/music-theory";
import { parseAsString, parseAsStringLiteral } from "nuqs";

export const BARRE_FILTERS = ["yes", "no"] as const;
export type BarreFilter = (typeof BARRE_FILTERS)[number];

export const chordSearchParsers = {
  type: parseAsStringLiteral(CHORD_TYPE_IDS),
  key: parseAsStringLiteral(CHORD_KEY_IDS),
  q: parseAsString.withDefault(""),
  barre: parseAsStringLiteral(BARRE_FILTERS),
};
