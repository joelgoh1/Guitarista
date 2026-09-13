"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Headphones, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import {
  healthQuery,
  recommendationsQuery,
  useRefreshRecommendations,
} from "@/lib/api/queries";
import { NoodleCard } from "./NoodleCard";

const SHELF_LIMIT = 6;

/**
 * Home-page shelf of songs picked from the Spotify listening pool. Renders
 * nothing at all when the API has no Spotify client id — noodle mode simply
 * does not exist for that install.
 */
export function ListeningShelf() {
  const health = useQuery(healthQuery());
  const features = health.data?.features;
  const connected = features?.spotify_connected === true;
  const recommendations = useQuery({
    ...recommendationsQuery(SHELF_LIMIT),
    enabled: connected,
  });
  const refresh = useRefreshRecommendations();

  if (!features || features.spotify_user !== true) return null;

  if (!connected) {
    return (
      <section aria-labelledby="listening" className="flex flex-col gap-4">
        <h2 id="listening" className="text-lg font-semibold tracking-tight">
          From your listening
        </h2>
        <EmptyState
          icon={Headphones}
          title="Connect Spotify"
          description="Guitarista can keep a handful of tabs ready from what you actually listen to."
          action={
            <Button variant="secondary" size="sm" nativeButton={false} render={<Link href="/settings" />}>
              Connect in settings
            </Button>
          }
        />
      </section>
    );
  }

  const entries = recommendations.data ?? [];

  return (
    <section aria-labelledby="listening" className="flex flex-col gap-4" data-testid="listening-shelf">
      <div className="flex items-end justify-between">
        <h2 id="listening" className="text-lg font-semibold tracking-tight">
          From your listening
        </h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          aria-label="Refresh recommendations"
        >
          {refresh.isPending ? (
            <Loader2 data-icon="inline-start" className="animate-spin" />
          ) : (
            <RefreshCw data-icon="inline-start" />
          )}
          Refresh
        </Button>
      </div>

      {recommendations.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <EmptyState
          icon={Headphones}
          title={recommendations.isError ? "Could not read your pool" : "Nothing here yet"}
          description={
            recommendations.isError
              ? "The API could not reach Spotify. Check the connection in settings."
              : "Guitarista is still building a pool from your listening history."
          }
          action={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
            >
              Refresh now
            </Button>
          }
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {entries.map((entry) => (
            <li key={entry.spotify_id}>
              <NoodleCard entry={entry} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
