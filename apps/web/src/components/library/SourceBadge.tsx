import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const SOURCE_LABELS: Record<string, string> = {
  songsterr: "Songsterr",
  ultimate_guitar: "Ultimate Guitar",
  audio: "Audio",
  score: "Score",
  manual: "Manual",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

export function SourceBadge({ source, className }: { source: string; className?: string }) {
  return (
    <Badge variant="outline" data-source={source} className={cn("capitalize", className)}>
      {sourceLabel(source)}
    </Badge>
  );
}
