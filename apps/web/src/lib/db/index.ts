import Dexie, { type EntityTable } from "dexie";

export interface ProgressRow {
  tabId: string;
  lastPositionMs: number;
  /** Playback speed multiplier (0.5 .. 1.5). */
  speed: number;
  updatedAt: number;
}

export interface SettingRow {
  key: string;
  value: unknown;
}

/**
 * Local-only persistence: per-tab playback progress and UI preferences.
 * The backend SQLite is the source of truth for songs/jobs/tabs.
 */
export class GuitaristaDB extends Dexie {
  progress!: EntityTable<ProgressRow, "tabId">;
  settings!: EntityTable<SettingRow, "key">;

  constructor() {
    super("guitarista");
    this.version(1).stores({
      progress: "tabId, updatedAt",
      settings: "key",
    });
  }
}

let instance: GuitaristaDB | null = null;

/** Returns null during SSR or when IndexedDB is unavailable. */
export function getDb(): GuitaristaDB | null {
  if (typeof window === "undefined" || typeof indexedDB === "undefined") return null;
  if (!instance) instance = new GuitaristaDB();
  return instance;
}

export async function readProgress(tabId: string): Promise<ProgressRow | undefined> {
  const db = getDb();
  if (!db) return undefined;
  try {
    return await db.progress.get(tabId);
  } catch {
    return undefined;
  }
}

export async function writeProgress(row: Omit<ProgressRow, "updatedAt">): Promise<void> {
  const db = getDb();
  if (!db) return;
  try {
    await db.progress.put({ ...row, updatedAt: Date.now() });
  } catch {
    // IndexedDB can be blocked (private mode); progress is best-effort.
  }
}

export async function readSetting<T>(key: string): Promise<T | undefined> {
  const db = getDb();
  if (!db) return undefined;
  try {
    const row = await db.settings.get(key);
    return row?.value as T | undefined;
  } catch {
    return undefined;
  }
}

export async function writeSetting(key: string, value: unknown): Promise<void> {
  const db = getDb();
  if (!db) return;
  try {
    await db.settings.put({ key, value });
  } catch {
    // best-effort
  }
}
