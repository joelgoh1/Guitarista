import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { queryKeys } from "@/lib/api/queries";
import type { EventSourceLike } from "@/lib/api/sse";
import type { Job } from "@/lib/api/types";
import { useJobEvents } from "@/hooks/useJobEvents";
import { makeTestQueryClient, withQueryClient } from "@/test/query";

class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onerror: ((ev: Event) => void) | null = null;
  onopen: ((ev: Event) => void) | null = null;
  closed = false;
  private listeners = new Map<string, Array<(ev: Event) => void>>();

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: (ev: Event) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }
  emit(type: string, payload: unknown) {
    const ev = new MessageEvent(type, { data: JSON.stringify(payload) });
    for (const fn of this.listeners.get(type) ?? []) fn(ev);
  }
  fail() {
    this.onerror?.(new Event("error"));
  }
}

const job = (patch: Partial<Job>): Job => ({
  id: "j1",
  status: "queued",
  request: { song: { raw: "x" }, capo: 0, cost_profile: "tabgen", origin: "user" },
  progress: 0,
  tiers: [],
  ...patch,
});

describe("useJobEvents", () => {
  it("reduces every event's job snapshot into the query cache and closes on end", () => {
    const qc = makeTestQueryClient();
    const factory = (url: string) => new FakeEventSource(url);
    const { result } = renderHook(() => useJobEvents("j1", { factory }), { wrapper: withQueryClient(qc) });
    const es = FakeEventSource.instances.at(-1)!;
    expect(es.url).toContain("/api/v1/jobs/j1/events");

    act(() => es.open());
    expect(result.current).toEqual({ connected: true, fallback: false });

    act(() => es.emit("tier", { tier: { tier: "songsterr", status: "running" }, job: job({ status: "running", tiers: [{ tier: "songsterr", status: "running" }] }) }));
    expect(qc.getQueryData<Job>(queryKeys.job("j1"))?.tiers?.[0]?.status).toBe("running");

    act(() => es.emit("progress", { progress: 0.5, message: "hi", job: job({ status: "running", progress: 0.5 }) }));
    expect(qc.getQueryData<Job>(queryKeys.job("j1"))?.progress).toBe(0.5);

    act(() => es.emit("done", { tab_id: "t1", job: job({ status: "done", tab_id: "t1", progress: 1 }) }));
    expect(qc.getQueryData<Job>(queryKeys.job("j1"))).toMatchObject({ status: "done", tab_id: "t1" });

    act(() => es.emit("end", { job_id: "j1" }));
    expect(es.closed).toBe(true);
    expect(result.current.connected).toBe(false);
  });

  it("falls back to polling when the stream errors", () => {
    const qc = makeTestQueryClient();
    const factory = (url: string) => new FakeEventSource(url);
    const { result } = renderHook(() => useJobEvents("j2", { factory }), { wrapper: withQueryClient(qc) });
    const es = FakeEventSource.instances.at(-1)!;
    act(() => es.fail());
    expect(es.closed).toBe(true);
    expect(result.current).toEqual({ connected: false, fallback: true });
  });

  it("does not connect for jobs already terminal in the cache", () => {
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.job("j3"), job({ id: "j3", status: "done", tab_id: "t" }));
    const before = FakeEventSource.instances.length;
    renderHook(() => useJobEvents("j3", { factory: (u) => new FakeEventSource(u) }), { wrapper: withQueryClient(qc) });
    expect(FakeEventSource.instances.length).toBe(before);
  });
});
