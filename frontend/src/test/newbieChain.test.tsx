import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NewbieGiftPopup from "@/components/newbie/NewbieGiftPopup";
import NewbieNextPage from "@/pages/NewbieNextPage";
import type { NewbieState } from "@/types";

let state: NewbieState;
const base = (): NewbieState => ({
  active: true, day: 1, first_pack_done: true, first_pack_top: "epic", squad_pack_done: false, squad_size: 11,
  arena_played: false, arena_claimed: false, arena_rarity: "legendary", tasks: [],
  gifts: [
    { day: 2, coins: 1000, card_rarity: null, opens_on: "2026-11-09", ready: false, claimed: false },
    { day: 3, coins: 0, card_rarity: "epic", opens_on: "2026-11-10", ready: false, claimed: false },
  ],
  bound_days: 0, steps_done: 1, steps_total: 10,
});

vi.mock("@/api/newbie", () => ({
  fetchNewbie: vi.fn(async () => state),
  openNewbieSquadPack: vi.fn(), claimNewbieStep: vi.fn(),
}));

function at(path: string, node: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={path} element={node} />
          <Route path="/" element={<p>home</p>} />
          <Route path="/play/arena" element={<p>arena</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("«Путь дебютанта» first session", () => {
  beforeEach(() => {
    state = base();
    sessionStorage.clear();
  });

  it("offers the team pack right after the debut pack", async () => {
    at("/newbie/next", <NewbieNextPage />);
    expect(await screen.findByText("Получить команду")).toBeTruthy();
  });

  it("then sends straight to the first Arena match", async () => {
    state.squad_pack_done = true;
    at("/newbie/next", <NewbieNextPage />);
    fireEvent.click(await screen.findByText("Сыграть первый матч"));
    expect(await screen.findByText("arena")).toBeTruthy();
  });

  it("goes home when the chain is done", async () => {
    state = { ...base(), squad_pack_done: true, arena_played: true };
    at("/newbie/next", <NewbieNextPage />);
    expect(await screen.findByText("home")).toBeTruthy();
  });

  it("shows a ready day gift as a popup on home, «Позже» hides it", async () => {
    state.gifts[0].ready = true;
    at("/", <NewbieGiftPopup />);
    expect(await screen.findByText("Ты вернулся — держи подарок")).toBeTruthy();
    fireEvent.click(screen.getByText("Позже"));
    expect(screen.queryByText("Ты вернулся — держи подарок")).toBeNull();
  });
});
