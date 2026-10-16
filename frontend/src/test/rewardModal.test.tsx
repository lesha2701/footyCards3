import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RewardModal, { RewardCoins } from "@/components/common/RewardModal";

vi.mock("@/lib/cardSkills", async (orig) => ({ ...(await orig()), useSkillCatalog: () => ({ data: undefined }) }));

afterEach(() => {
  delete window.Telegram;
});

describe("RewardModal", () => {
  it("shows the title, the rewards and closes from the button", () => {
    const onClose = vi.fn();
    render(<RewardModal title="Награда получена!" subtitle="День 3 серии" items={[<RewardCoins key="c" amount={150} />]} onClose={onClose} />);
    expect(screen.getByRole("dialog", { name: "Награда получена!" })).toBeInTheDocument();
    expect(screen.getByText("День 3 серии")).toBeInTheDocument();
    expect(screen.getByText(/\+150/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Отлично!"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape and on the backdrop, not on the panel", () => {
    const onClose = vi.fn();
    render(<RewardModal title="Приз" items={[]} onClose={onClose} />);
    fireEvent.click(screen.getByText("Приз"));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("celebrates a legendary reward with a tinted frame and a heavier haptic", () => {
    const impactOccurred = vi.fn();
    const notificationOccurred = vi.fn();
    window.Telegram = { WebApp: { HapticFeedback: { impactOccurred, notificationOccurred, selectionChanged: vi.fn() } } as never };
    render(<RewardModal title="Легенда!" rarity="legendary" items={[]} onClose={() => {}} />);
    expect(impactOccurred).toHaveBeenCalledWith("heavy");
    expect(notificationOccurred).toHaveBeenCalledWith("success");
    expect(document.querySelector(".shadow-glow-legendary")).not.toBeNull();
  });
});
