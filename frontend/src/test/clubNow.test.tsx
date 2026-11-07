import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ClubBackButton } from "@/components/clubs/ClubBackButton";
import { ClubNow } from "@/components/clubs/ClubNow";
import { ClubSheetContext } from "@/lib/clubSheet";
import type { Club, ClubWar, NextOpponent, TournamentCurrent } from "@/types";

const club = { rewards_unclaimed: 0, wall_unread: 0 } as Club;
const side = (name: string, score: number) => ({ club_id: 1, name, logo_shape: "shield", logo_color: "#FF0000", war_rating: 1000, score, members: [] });
const liveWar = { state: "active", ends_at: new Date(Date.now() + 3_600_000).toISOString(), me: side("Мы", 64), opponent: side("Они", 36) } as unknown as ClubWar;
const opponent: NextOpponent = { round_number: 3, opponent_club_id: 2, opponent_club_name: "Соперник", attack: 80, midfield: 81, defence: 82, goalkeeping: 83 };
const inTournament = { status: "active", tournament_id: 7, can_apply: false } as TournamentCurrent;

const show = (props: Partial<Parameters<typeof ClubNow>[0]>) => render(
  <MemoryRouter>
    <ClubNow club={club} isManager={false} pendingRequests={0} onApply={vi.fn()} applying={false} {...props} />
  </MemoryRouter>,
);

describe("ClubNow", () => {
  it("puts a live war first with the real score, the tournament goes to a row", () => {
    show({ war: liveWar, tournament: inTournament, nextOpponent: opponent });
    expect(screen.getByText("Идёт война")).toBeInTheDocument();
    expect(screen.getByText(/Ведём на 28/)).toBeInTheDocument();
    expect(screen.getByText("Тур 3: соперник Соперник")).toBeInTheDocument();
    expect(screen.queryByText("Атака")).not.toBeInTheDocument();
  });

  it("shows the next opponent when no war is on", () => {
    show({ tournament: inTournament, nextOpponent: opponent });
    expect(screen.getByText("Соперник")).toBeInTheDocument();
    expect(screen.getByText("Атака")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Изменить состав" })).not.toBeInTheDocument();
  });

  it("offers the tournament application to managers only", () => {
    const tournament = { status: "none", can_apply: true } as unknown as TournamentCurrent;
    show({ tournament, isManager: true });
    expect(screen.getByText(/подать заявку/)).toBeInTheDocument();
  });

  it("points to the quests when nothing is urgent", () => {
    show({ tournament: { status: "none", can_apply: true } as unknown as TournamentCurrent });
    expect(screen.queryByText(/подать заявку/)).not.toBeInTheDocument();
    expect(screen.getByText(/Срочных дел нет/)).toBeInTheDocument();
  });
});

describe("ClubBackButton", () => {
  it("closes the sheet when the section is shown in one", () => {
    const close = vi.fn();
    render(
      <MemoryRouter>
        <ClubSheetContext.Provider value={{ close }}>
          <ClubBackButton />
        </ClubSheetContext.Provider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(close).toHaveBeenCalledOnce();
  });
});
