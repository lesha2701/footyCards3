import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/sound", () => ({ playSound: vi.fn() }));
vi.mock("@/lib/music", () => ({ playChoir: vi.fn() }));
vi.mock("@/lib/pathCards", () => ({ pathFrameClass: () => "", talentByCode: () => null, usePathCatalog: () => ({ data: null }) }));

import { RevealStage } from "@/components/cards/CardRevealStage";
import { isWalkout, playerStageDuration, STAGE_DURATION_MS, WALKOUT_STAGE_DURATION_MS } from "@/components/cards/revealStages";
import { ALL_FLAG_CODES, countryCode } from "@/lib/countryFlags";
import type { Player } from "@/types";

const player = (over: Partial<Player> = {}): Player =>
  ({
    id: 1, display_name: "Тест Легенда", rarity: "legendary", rating: 93, attack_rating: 90, defense_rating: 50,
    country: "Бразилия", club: "Клуб", position: "ST", image_path: null, path_talent_code: null, collection_name: null,
    ...over,
  }) as unknown as Player;

const reveal = (p: Player, stage: Parameters<typeof RevealStage>[0]["stage"]) =>
  render(<RevealStage opened={{ card: { player: p }, is_new: true }} stage={stage} index={0} total={1} onTap={() => {}} />);

describe("legend walkout", () => {
  it("is only for legendary and diamond, never «Академия»", () => {
    expect(isWalkout(player())).toBe(true);
    expect(isWalkout(player({ rarity: "diamond" }))).toBe(true);
    expect(isWalkout(player({ rarity: "epic" }))).toBe(false);
    expect(isWalkout(player({ path_talent_code: "speed" }))).toBe(false);
    expect(playerStageDuration(player())).toBe(WALKOUT_STAGE_DURATION_MS);
    expect(playerStageDuration(player({ rarity: "rare" }))).toBe(STAGE_DURATION_MS);
  });

  it("maps Russian (and English) country names to flags", () => {
    expect(countryCode("Бразилия")).toBe("br");
    expect(countryCode(" аргентина ")).toBe("ar");
    expect(countryCode("Spain")).toBe("es");
    expect(countryCode("Англия")).toBe("gb-eng");
    expect(countryCode("Атлантида")).toBeNull();
    expect(countryCode(null)).toBeNull();
  });

  it("has a flag file for every code", () => {
    const files = Object.keys(import.meta.glob("../../../backend/static/flags/*.svg")).map((f) => f.split("/").pop());
    expect(ALL_FLAG_CODES.filter((c) => !files.includes(`${c}.svg`))).toEqual([]);
  });

  it("shows the flag, then the position, then the rating — no card yet", () => {
    reveal(player(), "country");
    expect(screen.getByTestId("legend-walkout")).toBeInTheDocument();
    expect(screen.getByTestId("walkout-flag").getAttribute("src")).toMatch(/flags\/br\.svg$/);
    expect(screen.queryByText("Тест Легенда")).toBeNull();
  });

  it("shows the position big on its stage", () => {
    reveal(player(), "club");
    expect(screen.getByText("ST")).toBeInTheDocument();
    expect(screen.getByText("Нападающий")).toBeInTheDocument();
  });

  it("counts the rating", () => {
    reveal(player(), "silhouette");
    expect(screen.getByTestId("walkout-rating")).toBeInTheDocument();
  });

  it("turns into the normal card on reveal", () => {
    reveal(player(), "reveal");
    expect(screen.queryByTestId("legend-walkout")).toBeNull();
    expect(screen.getByText("Тест Легенда")).toBeInTheDocument();
  });

  it("leaves regular cards alone", () => {
    reveal(player({ rarity: "epic" }), "country");
    expect(screen.queryByTestId("legend-walkout")).toBeNull();
    expect(screen.getByText("Бразилия")).toBeInTheDocument();
  });
});
