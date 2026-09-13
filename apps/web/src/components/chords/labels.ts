import {
  CHORD_KEYS,
  CHORD_KEY_IDS,
  CHORD_TYPES,
  type ChordKeyId,
  type ChordTypeId,
} from "@guitarista/music-theory";

export function keyLabel(key: ChordKeyId): string {
  return CHORD_KEYS.find((k) => k.id === key)?.label ?? key.toUpperCase();
}

export function keyFlatLabel(key: ChordKeyId): string | undefined {
  return CHORD_KEYS.find((k) => k.id === key)?.flatLabel;
}

export function typeLabel(type: ChordTypeId): string {
  return CHORD_TYPES.find((t) => t.id === type)?.label ?? type;
}

/** Short display name, e.g. `C♯m` / `G`. */
export function shortChordName(type: ChordTypeId, key: ChordKeyId): string {
  return `${keyLabel(key)}${type === "minor" ? "m" : ""}`;
}

export function chordHref(type: ChordTypeId, key: ChordKeyId) {
  return `/chords/${type}/${key}` as const;
}

export function isChordTypeId(v: string): v is ChordTypeId {
  return CHORD_TYPES.some((t) => t.id === v);
}

export function isChordKeyId(v: string): v is ChordKeyId {
  return (CHORD_KEY_IDS as readonly string[]).includes(v);
}

export function adjacentKey(key: ChordKeyId, delta: 1 | -1): ChordKeyId {
  const i = CHORD_KEY_IDS.indexOf(key);
  const n = CHORD_KEY_IDS.length;
  return CHORD_KEY_IDS[(i + delta + n) % n]!;
}
