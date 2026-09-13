import type { Route } from "next";
import {
  BookOpen,
  Dumbbell,
  FileMusic,
  Guitar,
  Home,
  Music2,
  Settings,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  title: string;
  href: Route;
  icon: LucideIcon;
  badge?: string;
  /** Extra path prefixes that should mark this item active. */
  matches?: string[];
}

export const NAV_ITEMS: NavItem[] = [
  { title: "Home", href: "/", icon: Home },
  { title: "Song → Tab", href: "/songs", icon: Music2, matches: ["/tabs"] },
  { title: "Score → Tab", href: "/score-to-tab", icon: FileMusic },
  { title: "Chords", href: "/chords", icon: Guitar },
  { title: "Library", href: "/library", icon: BookOpen },
  { title: "Practice", href: "/practice", icon: Dumbbell },
  { title: "Improv", href: "/improv", icon: Sparkles, badge: "soon" },
  { title: "Settings", href: "/settings", icon: Settings },
];

/** Human labels for breadcrumb segments. */
export const SEGMENT_LABELS: Record<string, string> = {
  songs: "Song → Tab",
  tabs: "Tabs",
  "score-to-tab": "Score → Tab",
  chords: "Chords",
  library: "Library",
  practice: "Practice",
  improv: "Improv",
  settings: "Settings",
  demo: "Demo",
  major: "Major",
  minor: "Minor",
  c: "C",
  "c_sharp": "C♯",
  d: "D",
  "d_sharp": "D♯",
  e: "E",
  f: "F",
  "f_sharp": "F♯",
  g: "G",
  "g_sharp": "G♯",
  a: "A",
  "a_sharp": "A♯",
  b: "B",
};

export function isNavActive(item: NavItem, pathname: string) {
  if (item.href === "/") return pathname === "/";
  if (pathname === item.href || pathname.startsWith(`${item.href}/`)) return true;
  return item.matches?.some((m) => pathname === m || pathname.startsWith(`${m}/`)) ?? false;
}
