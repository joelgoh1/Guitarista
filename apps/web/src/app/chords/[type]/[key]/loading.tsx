import { Skeleton } from "@/components/ui/skeleton";
import { PageContainer } from "@/components/common/PageContainer";

export default function Loading() {
  return (
    <PageContainer className="flex flex-col gap-6" aria-busy="true">
      <Skeleton className="h-8 w-40" />
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    </PageContainer>
  );
}
