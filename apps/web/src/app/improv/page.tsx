import type { Metadata } from "next";
import { Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeader } from "@/components/common/PageHeader";
import { ScaleExplorer } from "@/components/chords/ScaleExplorer";

export const metadata: Metadata = { title: "Improv" };

const IDEAS = [
  { title: "Scale picker over a progression", body: "Choose a progression from Practice and see which scales fit each chord change." },
  { title: "Backing track", body: "Loop the progression with a rhythm bed at your tempo and solo over it." },
  { title: "Phrase hints", body: "Target notes and licks suggested per chord change." },
];

export default function ImprovPage() {
  return (
    <PageContainer className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Improv"
        title="Improvise over anything"
        description="A guided space for soloing. The scale explorer works today; the rest is on the way."
        actions={<Badge>preview</Badge>}
      />
      <ScaleExplorer />
      <section aria-labelledby="coming" className="flex flex-col gap-3">
        <h2 id="coming" className="text-lg font-semibold tracking-tight">What is coming</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {IDEAS.map((i) => (
            <Card key={i.title}>
              <CardHeader>
                <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Sparkles className="size-4" aria-hidden />
                </span>
                <CardTitle className="text-base">{i.title}</CardTitle>
                <CardDescription>{i.body}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>
    </PageContainer>
  );
}
