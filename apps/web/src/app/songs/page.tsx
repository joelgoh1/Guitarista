import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeader } from "@/components/common/PageHeader";
import { SongInput } from "@/components/song/SongInput";

export const metadata: Metadata = { title: "Song → Tab" };

export default function SongsPage() {
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Song → Tab"
        title="Find a song"
        description="Paste a link, search by name, or upload audio. We'll try tab sources first and fall back to transcription."
      />
      {/* nuqs reads search params → needs a Suspense boundary for static rendering. */}
      <Suspense fallback={<Skeleton className="h-64 w-full max-w-2xl" />}>
        <SongInput />
      </Suspense>
    </PageContainer>
  );
}
