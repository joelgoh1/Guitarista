import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { getChord } from "@guitarista/music-theory";
import { ChordDiagram, computeFretWindow } from "@/components/chords/ChordDiagram";

const c = getChord("major", "c");

describe("ChordDiagram", () => {
  it("draws dots, open and muted markers for open C major", () => {
    const { container } = render(<ChordDiagram variation={c.variations["1"]!} title="C major" />);
    expect(container.querySelectorAll('[data-role="dot"]')).toHaveLength(3);
    expect(container.querySelectorAll('[data-role="open"]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-role="muted"]')).toHaveLength(1); // low E
    expect(container.querySelector('[data-role="barre"]')).toBeNull();
    expect(container.querySelector("title")).toHaveTextContent("C major");
    expect(container.querySelector('[data-role="fret-label"]')).toBeNull();
  });

  it("renders a barre and fret label for the 8th-fret C major voicing", () => {
    const v = c.variations["2"]!;
    const { container } = render(<ChordDiagram variation={v} />);
    const barre = container.querySelector('[data-role="barre"]');
    expect(barre).not.toBeNull();
    expect(barre?.tagName.toLowerCase()).toBe("rect");
    expect(container.querySelectorAll('[data-role="dot"]')).toHaveLength(6);
    expect(container.querySelectorAll('[data-role="muted"]')).toHaveLength(0);
    expect(container.querySelector('[data-role="fret-label"]')).toHaveTextContent("8fr");
    expect(computeFretWindow(v, 5)).toEqual({ startFret: 8, frets: 5, showNut: false });
  });

  it("shows finger numbers only when asked", () => {
    const { container, rerender } = render(<ChordDiagram variation={c.variations["1"]!} />);
    expect(container.querySelectorAll('[data-role="dot"] text')).toHaveLength(3);
    rerender(<ChordDiagram variation={c.variations["1"]!} showFingers={false} />);
    expect(container.querySelectorAll('[data-role="dot"] text')).toHaveLength(0);
  });
});
