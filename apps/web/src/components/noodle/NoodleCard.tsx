"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, Music2, Sparkles, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCreateJob, useDismissRecommendation } from "@/lib/api/queries";
import type { PoolEntry } from "@/lib/api/types";
import { evidenceLabel, noodleJobRequest } from "@/lib/noodle/pick";
import { cn } from "@/lib/utils";

/** Generating is in flight, nothing for the user to do but wait. */
const PENDING: ReadonlySet<PoolEntry["status"]> = new Set(["queued", "checking"]);

export function NoodleCard({ entry }: { entry: PoolEntry }) {
  const router = useRouter();
  const createJob = useCreateJob();
  const dismiss = useDismissRecommendation();

  const label = evidenceLabel(entry.evidence);
  const ready = entry.status === "ready" && !!entry.tab_id;
  const pending = PENDING.has(entry.status);

  const generate = () => {
    createJob.mutate(
      noodleJobRequest(entry),
      { onSuccess: (job) => router.push(`/songs/${job.id}`) },
    );
  };

  const body = (
    <Card
      className={cn(
        "h-full gap-0 overflow-hidden p-0 transition-colors",
        ready && "group-hover:border-primary/40 group-hover:bg-card/80",
      )}
    >
      <div className="flex items-start gap-3 p-3">
        {entry.artwork_url ? (
          // Local API artwork from Spotify's CDN; next/image would need a remote pattern.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={entry.artwork_url}
            alt={`Album art for ${entry.title} by ${entry.artist}`}
            className="size-14 shrink-0 rounded-lg object-cover"
            loading="lazy"
          />
        ) : (
          <span className="flex size-14 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Music2 className="size-5" aria-hidden />
          </span>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="truncate text-sm font-medium">{entry.title}</p>
          <p className="truncate text-xs text-muted-foreground">{entry.artist}</p>
          {label ? (
            <Badge variant="outline" className="mt-0.5" data-testid="evidence">
              {label}
            </Badge>
          ) : null}
        </div>
      </div>
      <div className="flex items-center gap-2 border-t border-border px-3 py-2">
        {ready ? (
          <span className="text-xs font-medium text-primary">Tab ready</span>
        ) : pending ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" aria-hidden />
            Preparing…
          </span>
        ) : (
          <Button
            size="xs"
            variant="secondary"
            onClick={generate}
            disabled={createJob.isPending}
            data-testid="generate"
          >
            {createJob.isPending ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <Sparkles data-icon="inline-start" />
            )}
            Generate
          </Button>
        )}
        {entry.status === "failed" ? (
          <span className="truncate text-xs text-muted-foreground">Last attempt failed</span>
        ) : null}
        <Button
          size="icon-xs"
          variant="ghost"
          className="ml-auto"
          aria-label={`Dismiss ${entry.title}`}
          onClick={() => dismiss.mutate(entry.spotify_id)}
          disabled={dismiss.isPending}
        >
          <X />
        </Button>
      </div>
    </Card>
  );

  if (ready) {
    return (
      <Link
        href={`/tabs/${entry.tab_id}`}
        className="group block rounded-xl outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        data-testid="noodle-card"
        data-status={entry.status}
      >
        {body}
      </Link>
    );
  }

  return (
    <div data-testid="noodle-card" data-status={entry.status}>
      {body}
    </div>
  );
}
