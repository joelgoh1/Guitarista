const RTF = typeof Intl !== "undefined" ? new Intl.RelativeTimeFormat("en", { numeric: "auto" }) : null;

const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 365 * 24 * 3600_000],
  ["month", 30 * 24 * 3600_000],
  ["week", 7 * 24 * 3600_000],
  ["day", 24 * 3600_000],
  ["hour", 3600_000],
  ["minute", 60_000],
];

/** "3 minutes ago", "yesterday", "just now". */
export function formatRelative(iso: string | Date | undefined | null, now = Date.now()): string {
  if (!iso) return "";
  const t = typeof iso === "string" ? Date.parse(iso) : iso.getTime();
  if (Number.isNaN(t)) return "";
  const diff = t - now;
  if (Math.abs(diff) < 45_000) return "just now";
  for (const [unit, ms] of UNITS) {
    if (Math.abs(diff) >= ms) {
      const value = Math.round(diff / ms);
      return RTF ? RTF.format(value, unit) : `${Math.abs(value)} ${unit}s ago`;
    }
  }
  return RTF ? RTF.format(Math.round(diff / 1000), "second") : "just now";
}

/** "0:42", "12:05", "1:02:03". */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = h ? m.toString().padStart(2, "0") : String(m);
  return `${h ? `${h}:` : ""}${mm}:${s.toString().padStart(2, "0")}`;
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}
