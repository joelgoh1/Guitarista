import { apiUrl } from "@/lib/api/client";
import type { Job } from "@/lib/api/types";

export type JobEventType = "tier" | "progress" | "done" | "error" | "end";

export interface JobEventHandlers {
  /** Called with the full job snapshot embedded in every event's payload. */
  onJob?: (job: Job, type: JobEventType) => void;
  onOpen?: () => void;
  /** The server closed the stream normally (after a terminal event). */
  onEnd?: () => void;
  /** The connection failed; callers should fall back to polling. */
  onError?: (event: Event) => void;
}

/** Structural subset of EventSource so tests can inject a fake. */
export interface EventSourceLike {
  addEventListener(type: string, listener: (ev: Event) => void): void;
  close(): void;
  readonly readyState: number;
  onerror: ((ev: Event) => void) | null;
  onopen: ((ev: Event) => void) | null;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

export function jobEventsUrl(jobId: string): string {
  return apiUrl(`/jobs/${encodeURIComponent(jobId)}/events`);
}

/** Extract the job snapshot from any event payload (`payload.job`). */
export function parseJobFromEvent(data: unknown): Job | null {
  if (typeof data !== "string") return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (parsed && typeof parsed === "object" && "job" in parsed) {
      const job = (parsed as { job?: unknown }).job;
      if (job && typeof job === "object" && "status" in job) return job as Job;
    }
  } catch {
    // ignore malformed frames
  }
  return null;
}

const defaultFactory: EventSourceFactory = (url) => new EventSource(url);

/**
 * Subscribe to `GET /jobs/{id}/events`. Returns an unsubscribe function.
 * On `end` the source is closed. On error the source is closed too: the
 * browser would otherwise retry forever, and the caller has polling anyway.
 */
export function subscribeJobEvents(
  jobId: string,
  handlers: JobEventHandlers,
  factory: EventSourceFactory = defaultFactory,
): () => void {
  const es = factory(jobEventsUrl(jobId));
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    es.close();
  };

  const forward = (type: JobEventType) => (ev: Event) => {
    const job = parseJobFromEvent((ev as MessageEvent).data);
    if (job) handlers.onJob?.(job, type);
  };

  for (const type of ["tier", "progress", "done", "error"] as const) {
    es.addEventListener(type, forward(type));
  }
  es.addEventListener("end", () => {
    close();
    handlers.onEnd?.();
  });
  es.onopen = () => handlers.onOpen?.();
  es.onerror = (ev) => {
    if (closed) return;
    close();
    handlers.onError?.(ev);
  };

  return close;
}
