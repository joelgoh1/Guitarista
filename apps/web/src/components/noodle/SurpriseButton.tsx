"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Shuffle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { fetchSurprise, healthQuery, useCreateJob } from "@/lib/api/queries";
import { toApiError } from "@/lib/api/problem";
import { noodleJobRequest } from "@/lib/noodle/pick";

/**
 * Hero button: opens a ready tab straight away, or starts a noodle job for the
 * best entry the pool has not generated yet. Only rendered once Spotify is
 * connected.
 */
export function SurpriseButton() {
  const router = useRouter();
  const health = useQuery(healthQuery());
  const createJob = useCreateJob();
  const [busy, setBusy] = React.useState(false);

  if (health.data?.features.spotify_connected !== true) return null;

  const surprise = async () => {
    setBusy(true);
    let pick;
    try {
      pick = await fetchSurprise();
    } catch (error) {
      const err = toApiError(error, "Could not pick a song");
      toast.error(
        err.status === 404
          ? "Nothing in your pool yet"
          : err.status === 409
            ? "Spotify is not connected"
            : err.title,
        { description: err.detail },
      );
      setBusy(false);
      return;
    }
    if (pick.tab_id) {
      router.push(`/tabs/${pick.tab_id}`);
      return;
    }
    // useCreateJob toasts its own failures.
    createJob.mutate(
      noodleJobRequest(pick.entry),
      {
        onSuccess: (job) => router.push(`/songs/${job.id}`),
        onError: () => setBusy(false),
      },
    );
  };

  return (
    <Button size="lg" variant="secondary" onClick={() => void surprise()} disabled={busy} data-testid="surprise">
      {busy ? (
        <Loader2 data-icon="inline-start" className="animate-spin" />
      ) : (
        <Shuffle data-icon="inline-start" />
      )}
      Surprise me
    </Button>
  );
}
