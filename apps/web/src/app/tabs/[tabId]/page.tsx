import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { TabDetail } from "@/components/library/TabDetail";

export const metadata: Metadata = { title: "Tab" };

export default async function TabPage({ params }: PageProps<"/tabs/[tabId]">) {
  const { tabId } = await params;
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 flex-col gap-6 p-8" aria-busy="true">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-24 w-full" />
        </div>
      }
    >
      <TabDetail tabId={tabId} />
    </Suspense>
  );
}
