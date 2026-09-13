import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { PianoKeys } from "@/components/chords/PianoKeys";

describe("PianoKeys", () => {
  it("highlights each given note once and marks the lowest as root", () => {
    const notes = ["C3", "E3", "G3", "C4", "E4"];
    const { container } = render(<PianoKeys highlighted={notes} />);
    expect(container.querySelectorAll('[data-highlighted="true"]')).toHaveLength(5);
    const root = container.querySelector('[data-root="true"]');
    expect(root?.getAttribute("data-note")).toBe("C3");
  });

  it("extends the range to include out-of-range notes and handles sharps", () => {
    const { container } = render(<PianoKeys highlighted={["C♯5", "F6"]} from="C2" to="C5" />);
    expect(container.querySelectorAll('[data-highlighted="true"]')).toHaveLength(2);
    expect(container.querySelector('[data-note="F6"]')).not.toBeNull();
  });
});
