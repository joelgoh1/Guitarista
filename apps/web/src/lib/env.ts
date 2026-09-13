import { z } from "zod";

// NEXT_PUBLIC_* vars are inlined at build time, so they must be referenced
// statically (no dynamic `process.env[key]`).
const schema = z.object({
  NEXT_PUBLIC_API_URL: z.url().default("http://localhost:8000"),
  /** Set to "false" to run alphaTab's renderer/synth on the main thread. */
  NEXT_PUBLIC_ALPHATAB_WORKERS: z.enum(["true", "false"]).default("true"),
});

export const env = schema.parse({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || undefined,
  NEXT_PUBLIC_ALPHATAB_WORKERS: process.env.NEXT_PUBLIC_ALPHATAB_WORKERS || undefined,
});

export type Env = z.infer<typeof schema>;
