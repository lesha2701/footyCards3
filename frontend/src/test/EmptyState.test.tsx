import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import EmptyState from "@/components/common/EmptyState";

describe("EmptyState", () => {
  it("renders the title and optional description", () => {
    render(<EmptyState title="Пусто" description="Ничего не найдено" />);
    expect(screen.getByText("Пусто")).toBeInTheDocument();
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
  });

  it("renders without a description", () => {
    render(<EmptyState title="Пусто" />);
    expect(screen.getByText("Пусто")).toBeInTheDocument();
  });
});
