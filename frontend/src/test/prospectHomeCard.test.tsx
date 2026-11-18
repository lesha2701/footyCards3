import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchProspect, type ProspectView } from "@/api/prospect";
import ProspectHomeCard from "@/components/home/ProspectHomeCard";

vi.mock("@/api/prospect", () => ({ fetchProspect: vi.fn() }));

const LOOK = { skin: 1, hair: 1, hair_color: 1, beard: 0, eye_color: 0, kit: 3, kit_pattern: 0 };
const STAGES = ["yard", "school", "youth", "u19", "debut"].map((code, i) => ({
  code, name: ["Двор", "Детская школа", "Юноши", "U-19", "Дебют"][i], emoji: "⚽", about: "", from_age: 6 + i * 3, cap: null,
}));

const base = (over: Partial<ProspectView>): ProspectView => ({
  enabled: true, balance: 0, stages: STAGES, positions: [], appearance_options: { skin: 6, hair: 14, hair_color: 7, beard: 5, eye_color: 6, kit: 10, kit_pattern: 4 },
  days_per_year: 8, start_age: 6, peak_range: [82, 90], prospect: null, ...over,
} as ProspectView);

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<ProspectHomeCard />} />
          <Route path="/academy/prospect" element={<p>prospect page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProspectHomeCard", () => {
  beforeEach(() => vi.mocked(fetchProspect).mockReset());

  it("invites to take a child when there is none", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(base({}));
    renderCard();
    expect(await screen.findByText("Вырасти своего игрока")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("prospect-home-card"));
    expect(await screen.findByText("prospect page")).toBeInTheDocument();
  });

  it("shows the growing child with today's events", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(base({
      prospect: {
        name: "Лёва", number: 10, position: "ST", foot: "right", appearance: LOOK, age: 9, age_days: 24, days_to_birthday: 8,
        stage: 1, stage_code: "school", rating: 37, stage_cap: 52, capped: false, banked_points: 0, xp: 4900, xp_in_point: 100,
        xp_per_point: 400, potential: null, peak: null, days_to_next_stage: 24, background: "bg_yard", accessory: null,
        owned_cosmetics: [], stats: {}, memories: [], atk_def: [40, 30], generation: 1, specs: [],
        peak_bonus: { dynasty: 0, academy: 0 }, universal: true, line: "MID", deficit: null,
      },
      spec_pick: { options: [], number: 1 },
      training: { free_available: true } as ProspectView["training"],
    }));
    renderCard();
    expect(await screen.findByText("Лёва")).toBeInTheDocument();
    expect(screen.getByText("37")).toBeInTheDocument();
    expect(screen.getByText("✨ Выбери талант")).toBeInTheDocument();
    expect(screen.getByText("🏋️ Тренировка")).toBeInTheDocument();
  });

  it("shows the graduate between generations", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(base({
      graduate: {
        id: 1, user_id: 1, name: "Тимур", number: 9, position: "ST", appearance: LOOK, rating: 87, potential: 4, generation: 1,
        status: "graduate", graduated_at: null, specs: [], stats: {}, background: "bg_yard", owner: null,
      },
    }));
    renderCard();
    expect(await screen.findByText("🌱 Новое поколение")).toBeInTheDocument();
    expect(screen.getByText("87")).toBeInTheDocument();
  });
});
