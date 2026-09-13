"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Music2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { jobsQuery, tabsQuery } from "@/lib/api/queries";
import { isTerminalJob } from "@/lib/api/types";
import { useNow } from "@/hooks/useNow";
import { JobStatusBadge } from "@/components/song/JobProgress";
import { TabCard } from "./TabCard";
import { formatRelative } from "./format";

/** Home page: last 6 tabs + last 5 jobs with status chips. */
export function RecentSection() {
  const tabs = useQuery(tabsQuery(6));
  const jobs = useQuery(jobsQuery(5));
  const now = useNow(30_000);
  const recentTabs = (tabs.data ?? []).slice(0, 6);
  const recentJobs = (jobs.data ?? []).slice(0, 5);

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="recent" className="flex flex-col gap-4">
        <div className="flex items-end justify-between">
          <h2 id="recent" className="text-lg font-semibold tracking-tight">
            Recent tabs
          </h2>
          <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/library" />}>
            Library
            <ArrowRight data-icon="inline-end" />
          </Button>
        </div>
        {tabs.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-36 w-full" />
            ))}
          </div>
        ) : recentTabs.length === 0 ? (
          <EmptyState
            icon={Music2}
            title={tabs.isError ? "API offline" : "No tabs yet"}
            description={
              tabs.isError
                ? "Start the Guitarista API to see your tabs here."
                : "Tabs you generate will show up here for quick access."
            }
            action={
              <Button variant="secondary" size="sm" nativeButton={false} render={<Link href="/songs" />}>
                Generate your first tab
              </Button>
            }
          />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {recentTabs.map((tab) => (
              <li key={tab.id}>
                <TabCard tab={tab} now={now} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {recentJobs.length > 0 ? (
        <section aria-labelledby="recent-jobs" className="flex flex-col gap-3">
          <h2 id="recent-jobs" className="text-sm font-semibold tracking-tight text-muted-foreground">
            Recent jobs
          </h2>
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border">
            {recentJobs.map((job) => {
              const song = job.request?.song;
              const label =
                [song?.artist, song?.title].filter(Boolean).join(" — ") ||
                song?.raw ||
                song?.spotify_url ||
                (job.request?.upload_id ? "Uploaded audio" : "Job");
              const href = job.status === "done" && job.tab_id ? `/tabs/${job.tab_id}` : `/songs/${job.id}`;
              return (
                <li key={job.id}>
                  <Link
                    href={href}
                    className="flex items-center gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-muted/50"
                  >
                    <JobStatusBadge status={job.status} />
                    <span className="min-w-0 flex-1 truncate">{label}</span>
                    <time className="shrink-0 text-xs text-muted-foreground" dateTime={job.created_at}>
                      {formatRelative(isTerminalJob(job) ? job.updated_at : job.created_at, now)}
                    </time>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
