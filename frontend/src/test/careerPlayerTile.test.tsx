import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { fetchCareerCollection, type CareerCollectionCard } from "@/api/career";
import { SquadBuilder } from "@/components/career/Offseason";
import { PlayerTile } from "@/components/career/PlayerTile";
import EmptyState from "@/components/common/EmptyState";
import { playerInfo } from "@/lib/careerPlayer";

vi.mock("@/api/career", async (orig) => ({ ...(await orig<object>()), fetchCareerCollection: vi.fn() }));

const card = (card_id: number, name: string, position: string, in_squad: boolean): CareerCollectionCard => ({
  card_id, in_squad, my_player: null,
  card: { player: { display_name: name, position, rating: 80, rarity: "rare", club: "", country: "" } } as never,
});

const wrap = (node: React.ReactNode) =>
  render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>);

describe("one player card in the career", () => {
  it("the tile: rating, position, surname; «Я» for my own player", () => {
    const mine = playerInfo({ card: null, my_player: { name: "Виктор Иванов ", position: "ST", rating: 77 } })!;
    render(<PlayerTile info={mine} />);
    expect(screen.getByText("Иванов")).toBeInTheDocument();
    expect(screen.getByText("77")).toBeInTheDocument();
    expect(screen.getByText("ST")).toBeInTheDocument();
    expect(screen.getByText("Я")).toBeInTheDocument();
  });

  it("the season squad sheet draws the same tiles, ✓ on the picked ones", async () => {
    vi.mocked(fetchCareerCollection).mockResolvedValue({
      squad_size: 22, cards: [card(1, "Игорь Акинфеев", "GK", true), card(2, "Пётр Петров", "CB", false)],
    } as never);
    wrap(<SquadBuilder onClose={vi.fn()} onView={vi.fn()} onError={vi.fn()} />);
    const picked = await screen.findByRole("button", { name: "Игорь Акинфеев, GK, 80" });
    expect(picked).toHaveAttribute("aria-pressed", "true");
    expect(picked).toHaveTextContent("✓");
    const other = screen.getByRole("button", { name: "Пётр Петров, CB, 80" });
    expect(other).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(other);
    expect(other).toHaveAttribute("aria-pressed", "true");
  });

  it("no cards yet: an empty state instead of empty lines", async () => {
    vi.mocked(fetchCareerCollection).mockResolvedValue({ squad_size: 22, cards: [] } as never);
    wrap(<SquadBuilder onClose={vi.fn()} onView={vi.fn()} onError={vi.fn()} />);
    expect(await screen.findByText("Пока некого заявить")).toBeInTheDocument();
  });
});

describe("compact empty state", () => {
  it("title, hint and action inside a card", () => {
    render(<EmptyState compact title="Трофеев пока нет" description="Титулы попадут сюда." action={<button>Ок</button>} />);
    expect(screen.getByText("Трофеев пока нет")).toBeInTheDocument();
    expect(screen.getByText("Титулы попадут сюда.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ок" })).toBeInTheDocument();
  });
});
