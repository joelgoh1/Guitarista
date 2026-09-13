import Link from "next/link";
import { ArrowRight, FileMusic, Guitar, Music2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageContainer } from "@/components/common/PageContainer";
import { RecentSection } from "@/components/library/RecentSection";
import { ListeningShelf } from "@/components/noodle/ListeningShelf";
import { SurpriseButton } from "@/components/noodle/SurpriseButton";

const FEATURES = [
  {
    title: "Song → Tab",
    description: "Paste a Spotify link or type a song. We find or generate a playable tab.",
    href: "/songs",
    icon: Music2,
  },
  {
    title: "Score → Tab",
    description: "Upload a score and get an ergonomic fretting for it.",
    href: "/score-to-tab",
    icon: FileMusic,
  },
  {
    title: "Chords",
    description: "Voicings on the fretboard and piano, with audio, for every key.",
    href: "/chords",
    icon: Guitar,
  },
] as const;

export default function HomePage() {
  return (
    <PageContainer className="flex flex-col gap-14">
      <section className="flex flex-col gap-6 pt-6 sm:pt-10">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-primary">Guitarista</p>
        <h1 className="max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
          Any song, on your fretboard, in minutes.
        </h1>
        <p className="max-w-xl text-base text-muted-foreground sm:text-lg">
          Search a song, drop a score, or upload audio. Guitarista turns it into an interactive
          tab you can slow down, loop and play along with.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button size="lg" nativeButton={false} render={<Link href="/songs" />}>
            <Music2 data-icon="inline-start" />
            Find a song
          </Button>
          <Button size="lg" variant="outline" nativeButton={false} render={<Link href="/tabs/demo" />}>
            <Play data-icon="inline-start" />
            Try the demo tab
          </Button>
          <SurpriseButton />
        </div>
      </section>

      <section aria-labelledby="features" className="flex flex-col gap-4">
        <h2 id="features" className="sr-only">
          Features
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <Link
              key={f.href}
              href={f.href}
              className="group rounded-xl outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              <Card className="h-full transition-colors group-hover:border-primary/40 group-hover:bg-card/80">
                <CardHeader className="gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <f.icon className="size-4" aria-hidden />
                  </span>
                  <CardTitle className="flex items-center gap-1.5 text-base">
                    {f.title}
                    <ArrowRight className="size-4 opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100" />
                  </CardTitle>
                  <CardDescription>{f.description}</CardDescription>
                </CardHeader>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      <RecentSection />

      <ListeningShelf />
    </PageContainer>
  );
}
