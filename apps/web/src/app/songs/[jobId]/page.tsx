import type { Metadata } from "next";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeader } from "@/components/common/PageHeader";
import { JobProgress } from "@/components/song/JobProgress";

export const metadata: Metadata = { title: "Generating tab" };

export default async function JobPage({ params }: PageProps<"/songs/[jobId]">) {
  const { jobId } = await params;
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Song → Tab"
        title="Generating your tab"
        description={
          <>
            Job <code className="font-mono text-xs">{jobId}</code>
          </>
        }
      />
      <JobProgress jobId={jobId} />
    </PageContainer>
  );
}
