import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PlayerCard from "@/components/cards/PlayerCard";
import CardStarPanel from "@/components/collection/CardStarPanel";
import { losesProgress, previewStarFeed, starString } from "@/lib/cardStars";
import type { CardStarState, Player } from "@/types";

const state = (over: Partial<CardStarState> = {}): CardStarState => ({
  card_id: 1, player_id: 1, rarity: "common", enabled: true, block_reason: null,
  stars: 0, max_stars: 3, progress: 7, thresholds: [10, 15, 25], coin_costs: [100, 200, 400],
  next_threshold: 10, next_coin_cost: 100, claimable: false, dupes_to_max: 43,
  rating_base: 80, rating_now: 80, rating_bonus: 0, rating_after_next_star: 81,
  free_duplicates: [], ...over,
});

vi.mock("@/api/collection", () => ({
  fetchCardStars: vi.fn(async () => state({
    free_duplicates: Array.from({ length: 5 }, (_, i) => ({ id: 10 + i, serial_number: 20 + i, skill_code: null, skill_level: null })),
  })),
  feedCardStars: vi.fn(),
  claimCardStar: vi.fn(),
}));

describe("previewStarFeed", () => {
  it("banks duplicates and claims every star the coins cover", () => {
    // 7 + 20 = 27: ★1 takes 10, ★2 takes 15, 2 left toward ★3.
    expect(previewStarFeed(state(), 20, 10_000)).toMatchObject({ consumed: 20, starsGained: 2, coinsSpent: 300, stars: 2, progress: 2 });
  });

  it("keeps progress when coins are missing and never feeds past the maximum", () => {
    expect(previewStarFeed(state(), 3, 50)).toMatchObject({ consumed: 3, starsGained: 0, progress: 10, waitingForCoins: true });
    expect(previewStarFeed(state({ dupes_to_max: 4 }), 30, 0).consumed).toBe(4);
  });

  it("formats stars and flags copies that would lose progress", () => {
    expect(starString(1, 3)).toBe("★☆☆");
    expect(losesProgress({ skill_code: null, stars: 0, star_progress: 3 })).toBe(true);
    expect(losesProgress({ skill_code: null, stars: 0, star_progress: 0 })).toBe(false);
  });
});

describe("star UI", () => {
  it("shows the stars of a copy on its card", () => {
    const player = {
      id: 1, display_name: "Игрок", rating: 82, position: "ST", rarity: "common", club: "К", country: "С",
      attack_rating: 80, defense_rating: 60, image_path: null, collection_name: null,
    } as unknown as Player;
    render(<PlayerCard player={player} stars={2} />);
    expect(screen.getByLabelText("Звёзд: 2")).toHaveTextContent("★★");
  });

  it("previews feeding all free duplicates before confirming", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <CardStarPanel cardId={1} isDiamond={false} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("7/10")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Вложить все дубли (5)"));
    expect(screen.getByText(/−5 дублей/)).toBeInTheDocument();
    expect(screen.getByText(/Вложенные дубли исчезнут/)).toBeInTheDocument();
  });

  it("renders nothing for a diamond card", () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <CardStarPanel cardId={1} isDiamond />
      </QueryClientProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
