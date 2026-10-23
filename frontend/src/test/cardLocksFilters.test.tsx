import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PlayerCard from "@/components/cards/PlayerCard";
import CardFilterBar from "@/components/collection/CardFilterBar";
import { EMPTY_FILTER, fromSaved, matchesPlayer, toSaved } from "@/lib/cardFilter";
import { cardLockProps, inSquad, squadLabel } from "@/lib/cardLocks";
import { planArenaPlacement } from "@/lib/lineupPlacement";
import type { Lineup, LineupSlot, Player, UserCard } from "@/types";

const saveMock = vi.fn(async (f: unknown) => f);
vi.mock("@/api/collection", () => ({
  fetchCardFilterOptions: async () => ({ countries: ["Бразилия", "Аргентина"], clubs: ["Сантос"] }),
  saveCardFilterDefault: (f: unknown) => saveMock(f),
}));

let nextId = 1;
function player(over: Partial<Player> = {}): Player {
  const id = nextId++;
  return {
    id, first_name: "A", last_name: `P${id}`, display_name: `Игрок ${id}`, rating: 70, rarity: "common",
    country: "Бразилия", club: "Сантос", position: "ST", image_path: null, quick_sell_price: 10,
    attack_rating: 70, defense_rating: 40, is_active: true, collection_id: null, ...over,
  } as Player;
}

function card(over: Partial<UserCard> = {}, p: Partial<Player> = {}): UserCard {
  return {
    id: nextId++, serial_number: 1, player: player(p), acquired_at: "2026-10-01T00:00:00Z", source: "pack",
    is_locked_by_admin: false, is_locked_in_trade: false, is_in_lineup: false, is_in_tactico_squad: false,
    hidden_from_trade: false, ...over,
  } as UserCard;
}

function slot(code: string, category: string, ideal: string, c: UserCard | null): LineupSlot {
  return { slot_code: code, category, ideal_position: ideal, card: c };
}

function lineup(slots: LineupSlot[], over: Partial<Lineup> = {}): Lineup {
  return {
    id: 1, template_index: 0, name: "Основа", is_active: true, formation: "4-3-3", tactic: "balanced",
    is_complete: true, team_strength: 70, max_diamond: 1, max_path: 1, coach: null, stadium: null, slots, ...over,
  } as Lineup;
}

describe("card locks", () => {
  it("knows every kind of squad and the owner's lock", () => {
    expect(inSquad(card({ is_in_lineup: true }))).toBe(true);
    expect(inSquad(card({ in_personal_squad: true }))).toBe(true);
    expect(squadLabel(card({ is_in_tactico_squad: true }))).toBe("в составе Тактико");
    expect(cardLockProps(card({ is_user_locked: true }))).toEqual({ inSquad: false, userLocked: true });
  });

  it("shades a squad copy and marks a locked one on the card face", () => {
    render(<PlayerCard player={player({ display_name: "Пеле" })} inSquad userLocked />);
    expect(screen.getByText("В составе")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Пеле.*в составе.*под замком/ })).toBeInTheDocument();
  });
});

describe("card filter", () => {
  it("matches players by rarity, country, club and position", () => {
    const p = player({ rarity: "rare", country: "Аргентина", club: "Ривер", position: "CM" });
    expect(matchesPlayer({ ...EMPTY_FILTER }, p)).toBe(true);
    expect(matchesPlayer({ ...EMPTY_FILTER, country: "Аргентина", position: "CM" }, p)).toBe(true);
    expect(matchesPlayer({ ...EMPTY_FILTER, club: "Бока" }, p)).toBe(false);
    expect(matchesPlayer({ ...EMPTY_FILTER, rarity: "epic" }, p)).toBe(false);
  });

  it("round-trips the saved default", () => {
    const f = { ...EMPTY_FILTER, rarity: "epic" as const, club: "Сантос", sort_by: "rating" as const };
    expect(fromSaved(toSaved(f))).toEqual(f);
    expect(fromSaved(null)).toEqual(EMPTY_FILTER);
  });

  it("saves the current filter as the default from the panel", async () => {
    const onChange = vi.fn();
    const current = { ...EMPTY_FILTER, country: "Бразилия" };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <CardFilterBar filter={current} onChange={onChange} defaultFilter={EMPTY_FILTER} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByText(/Фильтры/));
    fireEvent.click(screen.getByText("Сохранить по умолчанию"));
    await waitFor(() => expect(saveMock).toHaveBeenCalledWith(expect.objectContaining({ country: "Бразилия" })));
    expect(await screen.findByText(/Фильтр сохранён/)).toBeInTheDocument();
  });
});

describe("put a card into the Card Arena lineup from the card", () => {
  it("takes an empty slot of its line, ideal position first", () => {
    const st = card({}, { position: "ST" });
    const l = lineup([
      slot("GK", "GK", "GK", card({}, { position: "GK" })),
      slot("FWD1", "FWD", "LW", null),
      slot("FWD2", "FWD", "ST", null),
    ]);
    const plan = planArenaPlacement(l, st);
    expect(plan.ok && plan.slotCode).toBe("FWD2");
    expect(plan.ok && plan.replaced).toBeNull();
  });

  it("replaces the weakest card of its line when the line is full", () => {
    const weak = card({}, { position: "ST", rating: 60 });
    const strong = card({}, { position: "LW", rating: 85 });
    const plan = planArenaPlacement(
      lineup([slot("FWD1", "FWD", "LW", strong), slot("FWD2", "FWD", "ST", weak)]),
      card({}, { position: "ST", rating: 80 }),
    );
    expect(plan.ok && plan.replaced?.id).toBe(weak.id);
  });

  it("swaps out the «Академия» card when the limit is reached", () => {
    const pathInSquad = card({}, { position: "CM", rarity: "diamond", path_talent_code: "big_matches" });
    const newPath = card({}, { position: "ST", rarity: "diamond", path_talent_code: "hunger" });
    const blocked = planArenaPlacement(
      lineup([slot("MID1", "MID", "CM", pathInSquad), slot("FWD1", "FWD", "ST", null)]),
      newPath,
    );
    expect(blocked.ok).toBe(false);

    const fwdPath = card({}, { position: "ST", rarity: "diamond", path_talent_code: "big_matches" });
    const swapped = planArenaPlacement(lineup([slot("FWD1", "FWD", "ST", fwdPath), slot("FWD2", "FWD", "LW", null)]), newPath);
    expect(swapped.ok && swapped.replaced?.id).toBe(fwdPath.id);
  });

  it("refuses a position the formation has no line for", () => {
    expect(planArenaPlacement(lineup([slot("GK", "GK", "GK", null)]), card({}, { position: "ST" })).ok).toBe(false);
  });
});
