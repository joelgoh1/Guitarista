import type { Metadata } from "next";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeader } from "@/components/common/PageHeader";
import { ScoreUpload } from "@/components/score/ScoreUpload";

export const metadata: Metadata = { title: "Score → Tab" };

export default function ScoreToTabPage() {
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Score → Tab"
        title="Upload a score"
        description="Sheet music in, ergonomic fingering out. Pick the part to arrange for guitar."
      />
      <ScoreUpload />
    </PageContainer>
  );
}
