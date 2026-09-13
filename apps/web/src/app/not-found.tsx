import Link from "next/link";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageContainer } from "@/components/common/PageContainer";
import { EmptyState } from "@/components/common/EmptyState";

export default function NotFound() {
  return (
    <PageContainer className="flex items-center">
      <EmptyState
        className="w-full"
        icon={Compass}
        title="Page not found"
        description="That route doesn't exist. Maybe the tab was removed, or the link is off by a fret."
        action={
          <Button render={<Link href="/" />} variant="secondary">
            Back home
          </Button>
        }
      />
    </PageContainer>
  );
}
