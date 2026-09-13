import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";
import { ChordLibrary } from "@/components/chords/ChordLibrary";

function cards() {
  return document.querySelectorAll('[data-slot="chord-card"]').length;
}

describe("ChordLibrary", () => {
  it("shows every chord by default", () => {
    render(<ChordLibrary />, { wrapper: withNuqsTestingAdapter({ searchParams: {} }) });
    expect(cards()).toBe(24);
  });

  it("filters by type, key and search from the URL", () => {
    const { unmount } = render(<ChordLibrary />, {
      wrapper: withNuqsTestingAdapter({ searchParams: { type: "minor" } }),
    });
    expect(cards()).toBe(12);
    unmount();

    render(<ChordLibrary />, {
      wrapper: withNuqsTestingAdapter({ searchParams: { key: "c", barre: "yes" } }),
    });
    expect(cards()).toBe(2);
    expect(screen.getByText("C major")).toBeInTheDocument();
    expect(screen.getByText("C minor")).toBeInTheDocument();
  });

  it("shows an empty state for no matches", () => {
    render(<ChordLibrary />, { wrapper: withNuqsTestingAdapter({ searchParams: { q: "zzz" } }) });
    expect(cards()).toBe(0);
    expect(screen.getByText("No chords match")).toBeInTheDocument();
  });
});
