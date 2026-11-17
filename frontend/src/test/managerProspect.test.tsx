import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ManagerClub, ManagerProspect, ManagerView } from "@/api/manager";
import ManagerPitch from "@/components/manager/ManagerPitch";
import { ProspectClubSection, ProspectMeSection } from "@/components/manager/ProspectPanels";

const setManagerMarket = vi.fn();
const endManagerContract = vi.fn();
vi.mock("@/api/manager", () => ({
  setManagerMarket: (...args: unknown[]) => setManagerMarket(...args),
  endManagerContract: (...args: unknown[]) => endManagerContract(...args),
}));

const LOOK = { skin: 1, hair: 1, hair_color: 1, beard: 0, eye_color: 0, kit: 3, kit_pattern: 0 };
const kid = (over: Partial<ManagerProspect> = {}): ManagerProspect => ({
  name: "Лёва Мяч", position: "ST", rating: 48, age: 10, eligible: true, min_stage: "Детская школа", stage: "Детская школа",
  market_open: false, value: 150_000, contract: null, appearance: LOOK, number: 7, ...over,
});
const view = (prospect: ManagerProspect | null) => ({ prospect, rules: { live_wage_max: 3000 } }) as unknown as ManagerView;
const club = { trade_locked: false, prospect_starts: false } as unknown as ManagerClub;

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
}

describe("prospect in «Менеджер»", () => {
  it("club: a young prospect waits for his stage", () => {
    wrap(<ProspectClubSection view={view(kid({ eligible: false, age: 7, stage: "Двор" }))} club={club} busy={false} onStarts={() => {}} />);
    expect(screen.getByText(/сможет играть с этапа «Детская школа»/)).toBeInTheDocument();
    expect(screen.queryByText("Всегда в старте")).not.toBeInTheDocument();
  });

  it("club: toggles «Всегда в старте»", () => {
    const onStarts = vi.fn();
    wrap(<ProspectClubSection view={view(kid())} club={club} busy={false} onStarts={onStarts} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onStarts).toHaveBeenCalledWith(true);
  });

  it("club: without a prospect links to the Academy", () => {
    wrap(<ProspectClubSection view={view(null)} club={club} busy={false} onStarts={() => {}} />);
    expect(screen.getByRole("button", { name: "🧒 К воспитаннику" })).toBeInTheDocument();
  });

  it("me: «Ищу клуб» puts the prospect on the market", async () => {
    setManagerMarket.mockResolvedValue(view(kid({ market_open: true })));
    const onView = vi.fn();
    wrap(<ProspectMeSection view={view(kid())} onView={onView} onError={() => {}} />);
    fireEvent.click(screen.getByRole("checkbox"));
    await waitFor(() => expect(setManagerMarket).toHaveBeenCalledWith(true, "prospect"));
    expect(onView).toHaveBeenCalled();
  });

  it("me: shows his club while on a contract", () => {
    const contract = { id: 3, kind: "sign", club_name: "Ястребы", club_owner: "Коля", wage: 400, seasons_left: 2, goals: 1, matches_played: 4 };
    wrap(<ProspectMeSection view={view(kid({ contract: contract as never }))} onView={() => {}} onError={() => {}} />);
    expect(screen.getByText("«Ястребы»")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Забрать из клуба" })).toBeInTheDocument();
  });

  it("pitch: the prospect has his own label", () => {
    render(<ManagerPitch formation="4-3-3" xi={[{ slot: "FWD2", kind: "prospect", name: "Лёва Мяч", position: "ST", rating: 48, appearance: LOOK, number: 7 }]} />);
    expect(screen.getByText("Юниор")).toBeInTheDocument();
  });
});
