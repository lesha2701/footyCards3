import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PlayerCard from "@/components/cards/PlayerCard";
import type { Player } from "@/types";

const player: Player = {
  id: 1,
  first_name: "Lucas",
  last_name: "Silva",
  display_name: "Lucas Silva",
  rating: 88,
  rarity: "epic",
  country: "Brazil",
  club: "Nord United",
  position: "ST",
  image_path: null,
  quick_sell_price: 120,
  is_active: true,
  collection_id: null,
  collection_name: null,
};

describe("PlayerCard", () => {
  it("renders player name and rating", () => {
    render(<PlayerCard player={player} />);
    expect(screen.getByText("Lucas Silva")).toBeInTheDocument();
    expect(screen.getByText("88")).toBeInTheDocument();
  });

  it("calls onClick when tapped", () => {
    const onClick = vi.fn();
    render(<PlayerCard player={player} onClick={onClick} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("is disabled when no onClick handler is provided", () => {
    render(<PlayerCard player={player} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
