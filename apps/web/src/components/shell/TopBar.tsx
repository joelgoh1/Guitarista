"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { SEGMENT_LABELS } from "@/components/shell/nav";

function labelFor(segment: string) {
  const known = SEGMENT_LABELS[segment];
  if (known) return known;
  const decoded = decodeURIComponent(segment);
  // Dynamic ids: keep them short.
  return decoded.length > 18 ? `${decoded.slice(0, 8)}…${decoded.slice(-6)}` : decoded;
}

export function TopBar() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  const crumbs = segments.map((seg, i) => ({
    href: `/${segments.slice(0, i + 1).join("/")}`,
    label: labelFor(seg),
    last: i === segments.length - 1,
  }));

  return (
    <header className="sticky top-0 z-20 flex h-12 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-3 backdrop-blur supports-backdrop-filter:bg-background/60 sm:px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-1 h-4" />
      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center gap-1 text-sm text-muted-foreground">
          <li>
            <Link href="/" className="transition-colors hover:text-foreground">
              Home
            </Link>
          </li>
          {crumbs.map((c) => (
            <li key={c.href} className="flex min-w-0 items-center gap-1">
              <ChevronRight className="size-3.5 shrink-0 opacity-60" aria-hidden />
              {c.last ? (
                <span className="truncate font-medium text-foreground" aria-current="page">
                  {c.label}
                </span>
              ) : (
                // Intermediate crumbs may be dynamic paths without a page; plain text keeps
                // typed routes honest without asserting the route exists.
                <span className="truncate">{c.label}</span>
              )}
            </li>
          ))}
        </ol>
      </nav>
      <ThemeToggle />
    </header>
  );
}
