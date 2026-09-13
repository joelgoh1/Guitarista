import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { CHORD_KEY_IDS, CHORD_TYPE_IDS, getChord } from "@guitarista/music-theory";
import { PageContainer } from "@/components/common/PageContainer";
import { PageHeader } from "@/components/common/PageHeader";
import { ChordDetail } from "@/components/chords/ChordDetail";
import { isChordKeyId, isChordTypeId, keyLabel, typeLabel } from "@/components/chords/labels";

export const dynamicParams = false;

export function generateStaticParams() {
  return CHORD_TYPE_IDS.flatMap((type) => CHORD_KEY_IDS.map((key) => ({ type, key })));
}

export async function generateMetadata({
  params,
}: PageProps<"/chords/[type]/[key]">): Promise<Metadata> {
  const { type, key } = await params;
  if (!isChordTypeId(type) || !isChordKeyId(key)) return { title: "Chord" };
  return { title: getChord(type, key).name };
}

export default async function ChordDetailPage({ params }: PageProps<"/chords/[type]/[key]">) {
  const { type, key } = await params;
  if (!isChordTypeId(type) || !isChordKeyId(key)) notFound();
  const entry = getChord(type, key);

  return (
    <PageContainer>
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-1">
            <Link href="/chords" className="hover:underline">
              Chords
            </Link>
            <ChevronRight className="size-3" aria-hidden />
            <Link href={{ pathname: "/chords", query: { type } }} className="hover:underline">
              {typeLabel(type)}
            </Link>
            <ChevronRight className="size-3" aria-hidden />
            <span className="text-foreground/80">{keyLabel(key)}</span>
          </span>
        }
        title={entry.name}
        description="Voicings, fingering and sound. Pick a voicing, then strum it."
      />
      <ChordDetail type={type} key_={key} entry={entry} />
    </PageContainer>
  );
}
