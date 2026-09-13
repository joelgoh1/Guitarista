import type { Metadata } from "next";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeader } from "@/components/common/PageHeader";
import { PracticeSessionLoader } from "@/components/practice/PracticeSessionLoader";

export const metadata: Metadata = { title: "Practice" };

export default function PracticePage() {
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Practice"
        title="Progressions"
        description="Loop a chord progression at your tempo and build muscle memory."
      />
      <PracticeSessionLoader />
    </PageContainer>
  );
}
