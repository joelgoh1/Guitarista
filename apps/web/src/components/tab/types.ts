import type { StaveProfile } from "@/lib/stores/player";

export type TabSource =
  | { kind: "alphaTex"; tex: string }
  | { kind: "url"; url: string }
  | { kind: "arrayBuffer"; data: ArrayBuffer };

export interface TabViewerProps {
  source: TabSource;
  staveProfile?: StaveProfile;
  onReady?: () => void;
  onError?: (error: Error) => void;
  className?: string;
}
