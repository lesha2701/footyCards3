import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AgentBadge from "@/components/market/AgentBadge";

describe("AgentBadge", () => {
  it("shows the art and falls back to the emoji until the file exists", () => {
    const { container } = render(<AgentBadge />);
    expect(screen.getByText("Агент")).toBeTruthy();
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe("/market/agent-badge.webp");
    fireEvent.error(img!);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("🕴️");
  });
});
