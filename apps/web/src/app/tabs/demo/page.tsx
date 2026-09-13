import type { Metadata } from "next";
import { TabPlayer } from "@/components/tab/TabPlayer";
import { DEMO_ALPHATEX, DEMO_TITLE } from "@/fixtures/demo.alphatex";

export const metadata: Metadata = { title: DEMO_TITLE };

/** alphaTab spike: renders a fixture with playback controls, no API needed. */
export default function DemoTabPage() {
  return (
    <div className="flex h-[calc(100svh-3rem)] min-h-0 flex-1 flex-col">
      <TabPlayer source={{ kind: "alphaTex", tex: DEMO_ALPHATEX }} />
    </div>
  );
}
