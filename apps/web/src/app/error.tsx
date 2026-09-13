"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageContainer } from "@/components/common/PageContainer";
import { EmptyState } from "@/components/common/EmptyState";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <PageContainer className="flex items-center">
      <EmptyState
        className="w-full"
        icon={AlertTriangle}
        title="Something went wrong"
        description={error.message || "An unexpected error occurred while rendering this page."}
        action={
          <Button onClick={reset} variant="secondary">
            Try again
          </Button>
        }
      />
    </PageContainer>
  );
}
