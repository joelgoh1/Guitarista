"use client";

import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/api/queries";
import { subscribeJobEvents, type EventSourceFactory } from "@/lib/api/sse";
import { isTerminalJob, type Job } from "@/lib/api/types";

export interface UseJobEventsOptions {
  enabled?: boolean;
  /** Test seam: inject a fake EventSource constructor. */
  factory?: EventSourceFactory;
}

export interface JobEventsState {
  /** Stream is open and feeding the query cache. */
  connected: boolean;
  /** Stream failed; the job query should poll instead. */
  fallback: boolean;
}

/**
 * Streams `GET /jobs/{id}/events` into the `jobQuery(id)` cache. Every event
 * carries a full job snapshot, so reducing is a plain `setQueryData`.
 */
export function useJobEvents(
  jobId: string | undefined,
  { enabled = true, factory }: UseJobEventsOptions = {},
): JobEventsState {
  const queryClient = useQueryClient();
  const [state, setState] = React.useState<JobEventsState>(() => ({
    connected: false,
    // No EventSource (old browser / SSR shim): poll from the start.
    fallback: !factory && typeof EventSource === "undefined",
  }));

  React.useEffect(() => {
    if (!jobId || !enabled || typeof window === "undefined") return;
    if (!factory && typeof EventSource === "undefined") return;

    const cached = queryClient.getQueryData<Job>(queryKeys.job(jobId));
    if (isTerminalJob(cached)) return; // nothing left to stream

    const unsubscribe = subscribeJobEvents(
      jobId,
      {
        onOpen: () => setState({ connected: true, fallback: false }),
        onJob: (job) => {
          queryClient.setQueryData(queryKeys.job(jobId), job);
          if (isTerminalJob(job)) {
            void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
            if (job.tab_id) void queryClient.invalidateQueries({ queryKey: queryKeys.tabs });
          }
        },
        onEnd: () => setState({ connected: false, fallback: false }),
        onError: () => setState({ connected: false, fallback: true }),
      },
      factory,
    );
    return () => {
      unsubscribe();
    };
  }, [jobId, enabled, factory, queryClient]);

  return state;
}
