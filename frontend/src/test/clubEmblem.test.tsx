import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ClubLogo } from "@/components/clubs/ClubLogo";
import ClubEmblemPage from "@/pages/ClubEmblemPage";
import type { ClubEmblemState } from "@/types";

const EMPTY = { color2: null, pattern: null, symbol: null, letters: null, outline: null, outline_thin: false, effect: null };

const item = (id: number, kind: ClubEmblemState["items"][number]["kind"], style_key: string, name: string, coins: number, stars: number, unlocked = false) => ({
  id, kind, style_key, name, coins_price: coins, stars_price: stars, is_active: true, sort_order: id, unlocked,
});

const state: ClubEmblemState = {
  enabled: true, club_id: 1, logo_shape: "shield", logo_color: "#3B82F6", emblem: EMPTY,
  items: [
    item(1, "color2", "second_color", "Второй цвет", 2000, 0),
    item(2, "pattern", "checker", "Клетка", 3000, 0, true),
    item(3, "letters", "letters", "Буквы клуба", 3000, 0),
    item(4, "symbol", "crown", "Корона", 0, 75),
    item(5, "outline", "gold", "Золотая обводка", 0, 100),
    item(6, "effect", "sparkle", "Звёздное мерцание", 0, 150),
  ],
  budget: 5000, can_edit: true, can_spend_budget: true,
};

vi.mock("@/api/clubFeatures", () => ({
  fetchClubEmblem: vi.fn(async () => state),
  saveClubEmblem: vi.fn(),
  buyClubEmblemItem: vi.fn(),
  createClubEmblemInvoice: vi.fn(),
}));

describe("ClubLogo", () => {
  it("draws a plain one-colour logo without an emblem", () => {
    const { container } = render(<ClubLogo shape="circle" color="#FF0000" />);
    expect(container.querySelectorAll("path")).toHaveLength(1);
    expect(container.querySelector("clipPath")).toBeNull();
  });

  it("draws the paid layers on top", () => {
    const { container } = render(
      <ClubLogo
        shape="shield"
        color="#FF0000"
        size={80}
        emblem={{ ...EMPTY, pattern: "checker", letters: "ФК", outline: "gold", effect: "sparkle" }}
      />,
    );
    expect(container.querySelector("clipPath")).not.toBeNull();
    expect(screen.getByText("ФК")).toBeInTheDocument();
    expect(container.querySelector("linearGradient")).not.toBeNull();
    expect(container.querySelectorAll(".emblem-sparkle").length).toBeGreaterThan(0);
  });
});

describe("ClubEmblemPage", () => {
  it("shows prices and blocks saving a try-on of a locked layer", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ClubEmblemPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Эмблема клуба")).toBeInTheDocument();
    expect(screen.getByText("75")).toBeInTheDocument(); // crown, Stars
    expect(screen.getByText("Корона")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Корона"));
    expect(screen.getByText(/Примерка: Корона/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сначала открой элементы из примерки" })).toBeDisabled();

    // An unlocked layer can be put on and saved.
    fireEvent.click(screen.getAllByText("Нет")[1]); // symbol → none
    fireEvent.click(screen.getByText("Клетка"));
    expect(screen.getByRole("button", { name: "Сохранить эмблему" })).toBeEnabled();
  });
});
