import { Skeleton } from "@/components/ui/skeleton";
import { PageContainer } from "@/components/common/PageContainer";

export default function Loading() {
  return (
    <PageContainer className="flex flex-col gap-6" aria-busy="true">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-80" />
      <Skeleton className="h-40 w-full max-w-2xl" />
    </PageContainer>
  );
}
