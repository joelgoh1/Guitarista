import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeader } from "@/components/common/PageHeader";
import { ChordLibrary } from "@/components/chords/ChordLibrary";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Chords" };

export default function ChordsPage() {
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Chords"
        title="Chord library"
        description="Voicings on the fretboard and piano for every key. Filter, listen, then open a chord for the details."
      />
      <Suspense
        fallback={
          <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4" aria-busy>
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-56 w-full" />
            ))}
          </div>
        }
      >
        <ChordLibrary />
      </Suspense>
    </PageContainer>
  );
}
