"use client";

import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, postMultipart, unwrap } from "@/lib/api/client";
import { toastApiError } from "@/lib/api/problem";
import {
  isTerminalJob,
  type AudioUploadResponse,
  type CandidatesResponse,
  type CreateJobRequest,
  type Health,
  type Job,
  type PoolEntry,
  type PoolSummary,
  type ScoreTabRequest,
  type ScoreUploadResponse,
  type Song,
  type SpotifyStatus,
  type SurprisePick,
  type Tab,
  type TabSummary,
} from "@/lib/api/types";

export const JOB_POLL_INTERVAL_MS = 1500;

export const queryKeys = {
  health: ["health"] as const,
  jobs: ["jobs"] as const,
  jobList: (limit: number) => ["jobs", "list", limit] as const,
  job: (id: string) => ["jobs", id] as const,
  tabs: ["tabs"] as const,
  tabList: () => ["tabs", "list"] as const,
  songTabs: (songId: string) => ["tabs", "list", "song", songId] as const,
  tab: (id: string) => ["tabs", id] as const,
  tabAlphaTex: (id: string, track: number) => ["tabs", id, "alphatex", track] as const,
  spotifySearch: (q: string) => ["songs", "search", q] as const,
  candidates: (songId: string) => ["songs", songId, "candidates"] as const,
  spotifyStatus: ["spotify", "status"] as const,
  /** Root key for every recommendations list, whatever the limit. */
  recommendations: ["recommendations"] as const,
  recommendationList: (limit: number) => ["recommendations", "list", limit] as const,
};

export const healthQuery = () =>
  queryOptions({
    queryKey: queryKeys.health,
    queryFn: async (): Promise<Health> => unwrap(await api.GET("/api/v1/health")),
    staleTime: 60_000,
    retry: 0,
  });

export interface JobQueryOptions {
  /** When the SSE stream is connected the cache is fed by events; skip polling. */
  sseConnected?: boolean;
}

export const jobQuery = (id: string, { sseConnected = false }: JobQueryOptions = {}) =>
  queryOptions({
    queryKey: queryKeys.job(id),
    queryFn: async (): Promise<Job> =>
      unwrap(await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: id } } })) as Job,
    staleTime: 0,
    refetchInterval: (query) => {
      if (sseConnected) return false;
      if (isTerminalJob(query.state.data)) return false;
      return JOB_POLL_INTERVAL_MS;
    },
  });

export const jobsQuery = (limit = 20) =>
  queryOptions({
    queryKey: queryKeys.jobList(limit),
    queryFn: async (): Promise<Job[]> =>
      unwrap(await api.GET("/api/v1/jobs", { params: { query: { limit } } })) as Job[],
    staleTime: 5_000,
  });

export const tabQuery = (id: string) =>
  queryOptions({
    queryKey: queryKeys.tab(id),
    queryFn: async (): Promise<Tab> =>
      // The endpoint also declares text/plain (alphaTex) so the typed union collapses to unknown.
      unwrap(await api.GET("/api/v1/tabs/{tab_id}", { params: { path: { tab_id: id } } })) as Tab,
    staleTime: 5 * 60_000,
  });

/** alphaTex is exported one track per request (see services/export/alphatex.py). */
export const tabAlphaTexQuery = (id: string, track = 0) =>
  queryOptions({
    queryKey: queryKeys.tabAlphaTex(id, track),
    queryFn: async (): Promise<string> =>
      unwrap(
        await api.GET("/api/v1/tabs/{tab_id}", {
          params: { path: { tab_id: id }, query: { format: "alphatex", track } },
          parseAs: "text",
        }),
      ) as string,
    staleTime: 5 * 60_000,
  });

export const tabsQuery = (limit = 100) =>
  queryOptions({
    queryKey: queryKeys.tabList(),
    queryFn: async (): Promise<TabSummary[]> =>
      unwrap(await api.GET("/api/v1/tabs", { params: { query: { limit } } })),
    staleTime: 10_000,
  });

/** Tabs already stored for one song (`GET /tabs?song_id=`). */
export const songTabsQuery = (songId: string) =>
  queryOptions({
    queryKey: queryKeys.songTabs(songId),
    queryFn: async (): Promise<TabSummary[]> =>
      unwrap(await api.GET("/api/v1/tabs", { params: { query: { song_id: songId, limit: 100 } } })),
    staleTime: 10_000,
  });

export const CANDIDATES_LIMIT = 12;

/**
 * `POST /songs/{song_id}/candidates`: every version the fallback chain could
 * fetch for this song, ordered Songsterr → Ultimate Guitar → audio. A POST that
 * behaves like a read, so it lives in the query cache (5 min).
 */
export const candidatesQuery = (songId: string, limit = CANDIDATES_LIMIT) =>
  queryOptions({
    queryKey: queryKeys.candidates(songId),
    queryFn: async (): Promise<CandidatesResponse> =>
      unwrap(
        await api.POST("/api/v1/songs/{song_id}/candidates", {
          params: { path: { song_id: songId } },
          body: { limit },
        }),
      ),
    staleTime: 5 * 60_000,
    retry: 1,
  });

export interface SpotifySearchResult {
  songs: Song[];
  /** True when the backend answered with `X-Spotify: disabled`. */
  disabled: boolean;
}

export const spotifySearchQuery = (q: string, limit = 8) =>
  queryOptions({
    queryKey: queryKeys.spotifySearch(q),
    queryFn: async (): Promise<SpotifySearchResult> => {
      const result = await api.GET("/api/v1/songs/search", { params: { query: { q, limit } } });
      const songs = unwrap(result);
      return { songs, disabled: result.response.headers.get("x-spotify") === "disabled" };
    },
    enabled: q.trim().length >= 2,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CreateJobRequest): Promise<Job> =>
      // `origin` defaults to "user" server-side; fill it in so the generated body type is happy.
      unwrap(await api.POST("/api/v1/jobs", { body: { origin: "user", ...body } })) as Job,
    onSuccess: (job) => {
      qc.setQueryData(queryKeys.job(job.id), job);
      void qc.invalidateQueries({ queryKey: queryKeys.jobs });
      if (job.song_id) void qc.invalidateQueries({ queryKey: queryKeys.candidates(job.song_id) });
    },
    onError: (error) => {
      toastApiError(error, "Could not start the job");
    },
  });
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string): Promise<Job> =>
      unwrap(
        await api.POST("/api/v1/jobs/{job_id}/cancel", { params: { path: { job_id: jobId } } }),
      ) as Job,
    onSuccess: (job) => {
      qc.setQueryData(queryKeys.job(job.id), job);
      void qc.invalidateQueries({ queryKey: queryKeys.jobs });
    },
    onError: (error) => {
      toastApiError(error, "Could not cancel the job");
    },
  });
}

export function useUploadAudio() {
  return useMutation({
    mutationFn: (file: File) => postMultipart<AudioUploadResponse>("/uploads/audio", file),
    onError: (error) => {
      toastApiError(error, "Audio upload failed");
    },
  });
}

export function useUploadScore() {
  return useMutation({
    mutationFn: (file: File) => postMultipart<ScoreUploadResponse>("/uploads/score", file),
    onError: (error) => {
      toastApiError(error, "Score upload failed");
    },
  });
}

export function useConvertScore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ScoreTabRequest): Promise<Tab> =>
      unwrap(await api.POST("/api/v1/score/tab", { body })),
    onSuccess: (tab) => {
      if (tab.id) qc.setQueryData(queryKeys.tab(tab.id), tab);
      void qc.invalidateQueries({ queryKey: queryKeys.tabs });
    },
    // 422s are rendered inline by ScoreUpload (with a retry hint), so no toast here.
  });
}

// ---------------------------------------------------------------------------
// Noodle mode: Spotify account + listening pool
// ---------------------------------------------------------------------------

export const RECOMMENDATIONS_LIMIT = 12;

export const spotifyStatusQuery = () =>
  queryOptions({
    queryKey: queryKeys.spotifyStatus,
    queryFn: async (): Promise<SpotifyStatus> =>
      unwrap(await api.GET("/api/v1/spotify/status")),
    staleTime: 30_000,
    retry: 0,
  });

/** The listening pool, best score first. 409s while Spotify is not connected. */
export const recommendationsQuery = (limit = RECOMMENDATIONS_LIMIT) =>
  queryOptions({
    queryKey: queryKeys.recommendationList(limit),
    queryFn: async (): Promise<PoolEntry[]> =>
      unwrap(await api.GET("/api/v1/recommendations", { params: { query: { limit } } })),
    staleTime: 60_000,
    retry: 0,
  });

/** `GET /spotify/login` → the PKCE authorize URL the browser must navigate to. */
export async function fetchSpotifyLoginUrl(): Promise<string> {
  const { authorize_url } = unwrap(await api.GET("/api/v1/spotify/login"));
  return authorize_url;
}

/** One-shot pick; never cached — the whole point is a different answer each time. */
export async function fetchSurprise(): Promise<SurprisePick> {
  return unwrap(await api.GET("/api/v1/recommendations/surprise"));
}

export function useRefreshRecommendations() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<PoolSummary> =>
      unwrap(await api.POST("/api/v1/recommendations/refresh")),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.recommendations });
    },
    onError: (error) => {
      toastApiError(error, "Could not refresh recommendations");
    },
  });
}

/** Hides one entry for good; removed from every cached list before the request lands. */
export function useDismissRecommendation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (spotifyId: string): Promise<void> => {
      unwrap(
        await api.POST("/api/v1/recommendations/{spotify_id}/dismiss", {
          params: { path: { spotify_id: spotifyId } },
        }),
      );
    },
    onMutate: async (spotifyId) => {
      await qc.cancelQueries({ queryKey: queryKeys.recommendations });
      const previous = qc.getQueriesData<PoolEntry[]>({ queryKey: queryKeys.recommendations });
      for (const [key, entries] of previous) {
        if (!entries) continue;
        qc.setQueryData(
          key,
          entries.filter((e) => e.spotify_id !== spotifyId),
        );
      }
      return { previous };
    },
    onError: (error, _spotifyId, context) => {
      for (const [key, entries] of context?.previous ?? []) qc.setQueryData(key, entries);
      toastApiError(error, "Could not dismiss that song");
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.recommendations });
    },
  });
}

export function useDisconnectSpotify() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<void> => {
      unwrap(await api.DELETE("/api/v1/spotify/auth"));
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.health });
      void qc.invalidateQueries({ queryKey: queryKeys.spotifyStatus });
      void qc.invalidateQueries({ queryKey: queryKeys.recommendations });
    },
    onError: (error) => {
      toastApiError(error, "Could not disconnect Spotify");
    },
  });
}
