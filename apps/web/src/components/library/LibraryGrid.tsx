"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { parseAsString, useQueryState } from "nuqs";
import { BookOpen, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { tabsQuery } from "@/lib/api/queries";
import { toApiError } from "@/lib/api/problem";
import { useNow } from "@/hooks/useNow";
import { TabCard } from "./TabCard";
import { sourceLabel } from "./SourceBadge";

export function LibraryGrid() {
  const tabs = useQuery(tabsQuery());
  const [q, setQ] = useQueryState("q", parseAsString.withDefault(""));
  const now = useNow(60_000);

  const filtered = React.useMemo(() => {
    const list = tabs.data ?? [];
    const needle = q.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((t) =>
      [t.title, t.artist ?? "", sourceLabel(t.source)].some((s) => s.toLowerCase().includes(needle)),
    );
  }, [tabs.data, q]);

  return (
    <div className="flex flex-col gap-6">
      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          aria-label="Filter tabs"
          placeholder="Filter by title, artist or source"
          value={q}
          onChange={(e) => void setQ(e.target.value || null)}
          className="pl-8"
        />
      </div>

      {tabs.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full" />
          ))}
        </div>
      ) : tabs.isError ? (
        <EmptyState
          icon={BookOpen}
          title="Couldn't load your library"
          description={toApiError(tabs.error).detail}
          action={
            <Button variant="secondary" size="sm" onClick={() => void tabs.refetch()}>
              Retry
            </Button>
          }
        />
      ) : (tabs.data ?? []).length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="Your library is empty"
          description="Generate a tab from a song or a score and it will be saved here."
          action={
            <Button variant="secondary" size="sm" nativeButton={false} render={<Link href="/songs" />}>
              Find a song
            </Button>
          }
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Search}
          title={`No tabs match “${q}”`}
          action={
            <Button variant="ghost" size="sm" onClick={() => void setQ(null)}>
              Clear filter
            </Button>
          }
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((tab) => (
            <li key={tab.id}>
              <TabCard tab={tab} now={now} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
