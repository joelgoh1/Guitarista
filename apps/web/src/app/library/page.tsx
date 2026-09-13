import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeader } from "@/components/common/PageHeader";
import { LibraryGrid } from "@/components/library/LibraryGrid";

export const metadata: Metadata = { title: "Library" };

export default function LibraryPage() {
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Library"
        title="Your tabs"
        description="Everything you've generated, stored locally."
      />
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <LibraryGrid />
      </Suspense>
    </PageContainer>
  );
}
