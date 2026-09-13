import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeader } from "@/components/common/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { SpotifyCard } from "@/components/settings/SpotifyCard";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Settings"
        title="Settings"
        description="Connections and preferences for this local install."
      />
      {/* nuqs reads the ?spotify= callback params → needs a Suspense boundary. */}
      <Suspense fallback={<Skeleton className="h-64 w-full max-w-2xl" />}>
        <div className="max-w-2xl">
          <SpotifyCard />
        </div>
      </Suspense>
    </PageContainer>
  );
}
