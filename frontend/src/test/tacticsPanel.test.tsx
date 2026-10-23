import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ManagerTacticsRules } from "@/api/manager";
import TacticsPanel from "@/components/manager/TacticsPanel";

const RULES: ManagerTacticsRules = {
  styles: [
    { value: "attacking", label: "Атака", about: "Нападение +6%", beats: "defensive", beats_label: "Оборона", reason: "штурм" },
    { value: "possession", label: "Владение", about: "Полузащита +6%", beats: "counter", beats_label: "Контратака", reason: "мяч у нас" },
    { value: "defensive", label: "Оборона", about: "Защита +6%", beats: "possession", beats_label: "Владение", reason: "блок" },
    { value: "counter", label: "Контратака", about: "Нападение и защита +3%", beats: "attacking", beats_label: "Атака", reason: "в спину" },
  ],
  formations: [{ value: "4-3-3", label: "4-3-3", attack: 0, defense: 0 }, { value: "3-4-3", label: "3-4-3", attack: 4, defense: -4 }],
  edge_pct: 4,
};

describe("TacticsPanel (Личный турнир / Менеджер)", () => {
  it("shows the next opponent's style, picks a style and a formation, explains the match", () => {
    const onChange = vi.fn();
    render(
      <TacticsPanel style="attacking" formation="4-3-3" rules={RULES} busy={false} onChange={onChange}
        next={{ opponent: "Коля", detail: "тур 3", style: "defensive", formation: "5-3-2", edge: "win", mods: { GK: 0, DEF: 0, MID: 6, FWD: 10 } }}
        help={<p>Правила турнира</p>} />,
    );
    expect(screen.getByTestId("tactics")).toHaveTextContent("Следующий соперник: Коля · тур 3");
    expect(screen.getByText(/твой стиль бьёт их \(\+4% ко всем\)/)).toBeInTheDocument();
    expect(screen.getByTestId("tactics")).toHaveTextContent("Атака +10%");
    fireEvent.click(screen.getByRole("button", { name: /^⚡ Контратака/ }));
    expect(onChange).toHaveBeenCalledWith({ style: "counter" });
    fireEvent.click(screen.getByRole("button", { name: /^3-4-3/ }));
    expect(onChange).toHaveBeenCalledWith({ formation: "3-4-3" });
    fireEvent.click(screen.getByRole("button", { name: "Как считается матч?" }));
    expect(screen.getByTestId("match-help")).toHaveTextContent("Правила турнира");
  });
});
