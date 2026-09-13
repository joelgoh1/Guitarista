import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PageHeader } from "@/components/common/PageHeader";

describe("PageHeader", () => {
  it("renders title, description, eyebrow and actions", () => {
    render(
      <PageHeader
        eyebrow="Library"
        title="Your tabs"
        description="Everything you've generated."
        actions={<button type="button">New</button>}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Your tabs" })).toBeInTheDocument();
    expect(screen.getByText("Library")).toBeInTheDocument();
    expect(screen.getByText("Everything you've generated.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New" })).toBeInTheDocument();
  });

  it("omits optional parts", () => {
    render(<PageHeader title="Plain" />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Plain");
    expect(screen.queryByRole("button")).toBeNull();
  });
});
