import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import NewbieWelcome from "@/components/newbie/NewbieWelcome";

vi.mock("@/api/newbie", () => ({
  fetchNewbie: vi.fn(async () => ({ active: true, first_pack_done: false, first_pack_top: "epic" })),
  openNewbieFirstPack: vi.fn(),
}));

describe("NewbieWelcome", () => {
  it("greets a new player on the stadium with the debut pack and one button", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <NewbieWelcome onFinish={() => {}} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Твой первый пак/)).toBeInTheDocument();
    expect(screen.getByAltText("Пак дебютанта").getAttribute("src")).toContain("packs/debut.webp");
    expect(screen.getByText("эпическая")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Открыть пак" })).toBeEnabled();
  });
});
