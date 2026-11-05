import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AcademyPicker from "./AcademyPicker";

const options = Array.from({ length: 30 }, (_, i) => ({ card_id: i + 1, name: `Игрок ${i + 1}`, position: i % 2 ? "ST" : "CB", rating: 60 + i }));
const base = { options, locked: false, busy: false, onPick: () => {}, onClear: () => {} };

describe("AcademyPicker", () => {
  it("shows only the chosen card until asked for the list", () => {
    render(<AcademyPicker {...base} selected={3} />);
    expect(screen.getAllByText(/Игрок \d+/)).toHaveLength(1);
    fireEvent.click(screen.getByText("Сменить"));
    expect(screen.getAllByText(/Игрок \d+/).length).toBeGreaterThan(30);
  });

  it("opens by itself when nobody is chosen, best first, and searches", () => {
    render(<AcademyPicker {...base} selected={null} />);
    expect(screen.getAllByRole("button")[0].textContent).toContain("Игрок 30");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "игрок 7" } });
    expect(screen.getAllByText(/Игрок \d+/)).toHaveLength(1);
  });

  it("picks and folds the list back", () => {
    const onPick = vi.fn();
    render(<AcademyPicker {...base} selected={3} onPick={onPick} />);
    fireEvent.click(screen.getByText("Сменить"));
    fireEvent.click(screen.getByText("Игрок 12"));
    expect(onPick).toHaveBeenCalledWith(12);
    expect(screen.getAllByText(/Игрок \d+/)).toHaveLength(1);
  });

  it("before a locked season there is nothing to change", () => {
    render(<AcademyPicker {...base} selected={3} locked />);
    expect(screen.queryByText("Сменить")).toBeNull();
  });
});
