"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { Check, Loader2, LogOut, RefreshCw, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  fetchSpotifyLoginUrl,
  healthQuery,
  spotifyStatusQuery,
  useDisconnectSpotify,
  useRefreshRecommendations,
} from "@/lib/api/queries";
import { toastApiError } from "@/lib/api/problem";
import type { PoolSummary } from "@/lib/api/types";

const REDIRECT_URI = "http://127.0.0.1:8000/api/v1/spotify/callback";

/** Human text for the `reason` the callback redirect can carry. */
function reasonText(reason: string | null): string {
  switch (reason) {
    case "state":
      return "The login attempt expired or was started somewhere else. Try connecting again.";
    case "denied":
      return "You declined the permissions Guitarista asked for.";
    case "token":
      return "Spotify refused the token exchange. Check the client id and redirect URI.";
    default:
      return reason ? `Spotify returned: ${reason}` : "Spotify did not complete the connection.";
  }
}

export function SpotifyCard() {
  const health = useQuery(healthQuery());
  const status = useQuery(spotifyStatusQuery());
  const disconnect = useDisconnectSpotify();
  const refresh = useRefreshRecommendations();
  const [connecting, setConnecting] = React.useState(false);
  const [summary, setSummary] = React.useState<PoolSummary | null>(null);

  // The OAuth callback bounces the browser back to /settings?spotify=…
  // Captured on the first render so the notice survives clearing the params.
  const [callback, setCallback] = useQueryState("spotify");
  const [reason, setReason] = useQueryState("reason");
  const [notice] = React.useState<{ kind: "ok" | "error"; text: string } | null>(() => {
    if (!callback) return null;
    if (callback === "connected") {
      return { kind: "ok", text: "Spotify connected. Your listening pool is being built." };
    }
    return { kind: "error", text: reasonText(reason) };
  });

  // Announce it once, then drop the params so a reload does not repeat it.
  const announced = React.useRef(false);
  React.useEffect(() => {
    if (!notice || announced.current) return;
    announced.current = true;
    if (notice.kind === "ok") toast.success("Spotify connected");
    else toast.error("Spotify could not be connected", { description: notice.text });
    void setCallback(null);
    void setReason(null);
  }, [notice, setCallback, setReason]);

  const configured = status.data?.configured ?? health.data?.features.spotify_user ?? false;
  const connected = status.data?.connected ?? health.data?.features.spotify_connected ?? false;

  const connect = async () => {
    setConnecting(true);
    try {
      const url = await fetchSpotifyLoginUrl();
      window.location.assign(url);
    } catch (error) {
      setConnecting(false);
      toastApiError(error, "Could not start the Spotify login");
    }
  };

  return (
    <Card data-testid="spotify-card">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>Spotify</CardTitle>
          {status.isPending ? null : connected ? (
            <Badge variant="secondary" data-testid="spotify-state">
              <Check data-icon="inline-start" /> Connected
            </Badge>
          ) : (
            <Badge variant="outline" data-testid="spotify-state">
              {configured ? "Not connected" : "Not configured"}
            </Badge>
          )}
        </div>
        <CardDescription>
          Connecting your account lets Guitarista build a pool of tabs from what you actually
          listen to, and powers “Surprise me”.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {notice ? (
          <p
            role="status"
            className={
              notice.kind === "ok"
                ? "rounded-lg border border-primary/40 bg-primary/10 p-3 text-sm"
                : "rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
            }
          >
            {notice.text}
          </p>
        ) : null}

        {!configured ? (
          <div className="flex flex-col gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
            <p className="flex items-center gap-2 font-medium">
              <TriangleAlert className="size-4" aria-hidden />
              No Spotify client id on the API
            </p>
            <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
              <li>
                Create an app at the Spotify developer dashboard and set{" "}
                <code className="font-mono">GUITARISTA_SPOTIFY_CLIENT_ID</code> in{" "}
                <code className="font-mono">apps/api/.env</code>.
              </li>
              <li>
                Register the redirect URI exactly as{" "}
                <code className="font-mono break-all">{REDIRECT_URI}</code> — Spotify only accepts
                the literal loopback address, not <code className="font-mono">localhost</code>.
              </li>
              <li>Add your own account under Users &amp; Access, or the API gets a 403.</li>
              <li>Restart the API and reload this page.</li>
            </ol>
          </div>
        ) : connected ? (
          <>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Account</dt>
              <dd className="truncate font-medium">
                {status.data?.display_name ?? status.data?.spotify_user_id ?? "Spotify user"}
              </dd>
              {status.data?.scopes?.length ? (
                <>
                  <dt className="text-muted-foreground">Scopes</dt>
                  <dd className="truncate text-muted-foreground">
                    {status.data.scopes.join(", ")}
                  </dd>
                </>
              ) : null}
            </dl>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                onClick={() =>
                  refresh.mutate(undefined, { onSuccess: (result) => setSummary(result) })
                }
                disabled={refresh.isPending}
              >
                {refresh.isPending ? (
                  <Loader2 data-icon="inline-start" className="animate-spin" />
                ) : (
                  <RefreshCw data-icon="inline-start" />
                )}
                Refresh recommendations now
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setSummary(null);
                  disconnect.mutate();
                }}
                disabled={disconnect.isPending}
              >
                <LogOut data-icon="inline-start" />
                Disconnect
              </Button>
            </div>
            {summary ? (
              <p className="text-sm text-muted-foreground" data-testid="pool-summary">
                {summary.skipped
                  ? "The pool was still fresh, so nothing was fetched."
                  : `${summary.fetched} tracks seen · ${summary.new} new · ${summary.available} playable · ${summary.ready} already in your library.`}
                {summary.errors?.length ? ` Problems: ${summary.errors.join(", ")}.` : ""}
              </p>
            ) : null}
          </>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              You will be sent to Spotify to approve read-only access to your top tracks, recently
              played and liked songs.
            </p>
            <div>
              <Button onClick={() => void connect()} disabled={connecting}>
                {connecting ? <Loader2 data-icon="inline-start" className="animate-spin" /> : null}
                Connect Spotify
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
