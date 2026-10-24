import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PrimaryActionButton from "@/components/common/PrimaryActionButton";
import { setClosingConfirmation, shareToTelegram } from "@/lib/telegram";
import { useKeyboardOpen } from "@/lib/useKeyboardOpen";
import { useUiStore } from "@/store/uiStore";

afterEach(() => {
  delete window.Telegram;
  localStorage.clear();
  vi.useRealTimers();
});

function mainButton() {
  return {
    setText: vi.fn(), show: vi.fn(), hide: vi.fn(), enable: vi.fn(), disable: vi.fn(),
    showProgress: vi.fn(), hideProgress: vi.fn(), onClick: vi.fn(), offClick: vi.fn(),
  };
}

describe("PrimaryActionButton", () => {
  it("renders a regular button outside Telegram", () => {
    const onClick = vi.fn();
    render(<PrimaryActionButton text="Начать игру" onClick={onClick} />);
    fireEvent.click(screen.getByText("Начать игру"));
    expect(onClick).toHaveBeenCalled();
  });

  it("stays an in-page button inside Telegram too (never the native MainButton)", () => {
    const button = mainButton();
    window.Telegram = { WebApp: { initData: "x", MainButton: button } as never };
    const onClick = vi.fn();
    render(<PrimaryActionButton text="Начать игру" onClick={onClick} />);
    fireEvent.click(screen.getByText("Начать игру"));
    expect(onClick).toHaveBeenCalled();
    expect(button.show).not.toHaveBeenCalled();
  });
});

describe("useKeyboardOpen", () => {
  it("is true while a text field is focused, not for checkboxes", async () => {
    vi.useFakeTimers();
    const input = document.createElement("input");
    const checkbox = Object.assign(document.createElement("input"), { type: "checkbox" });
    document.body.append(input, checkbox);
    const { result } = renderHook(() => useKeyboardOpen());
    expect(result.current).toBe(false);

    act(() => input.focus());
    expect(result.current).toBe(true);

    act(() => checkbox.focus());
    await act(async () => { vi.runAllTimers(); });
    expect(result.current).toBe(false);
    input.remove();
    checkbox.remove();
  });
});

describe("Telegram chrome helpers", () => {
  it("toggles closing confirmation only inside Telegram", () => {
    const enable = vi.fn();
    const disable = vi.fn();
    setClosingConfirmation(true); // no Telegram: no-op, no throw
    window.Telegram = { WebApp: { initData: "x", enableClosingConfirmation: enable, disableClosingConfirmation: disable } as never };
    setClosingConfirmation(true);
    setClosingConfirmation(false);
    expect(enable).toHaveBeenCalledTimes(1);
    expect(disable).toHaveBeenCalledTimes(1);
  });

  it("paints Telegram's bottom bar with the nav surface colour", () => {
    const setBottomBarColor = vi.fn();
    window.Telegram = { WebApp: { initData: "x", colorScheme: "dark", setBottomBarColor } as never };
    useUiStore.getState().setPreference("dark");
    expect(setBottomBarColor).toHaveBeenCalledWith("#10140f");
  });

  it("shares a prepared message natively, else opens the share link", async () => {
    const shareMessage = vi.fn((_id: string, cb?: (sent: boolean) => void) => cb?.(true));
    const openTelegramLink = vi.fn();
    window.Telegram = { WebApp: { initData: "x", shareMessage, openTelegramLink } as never };
    await expect(shareToTelegram("prep-1", "https://t.me/share/url?x")).resolves.toBe(true);
    expect(shareMessage).toHaveBeenCalledWith("prep-1", expect.any(Function));

    await expect(shareToTelegram(null, "https://t.me/share/url?x")).resolves.toBe(false);
    expect(openTelegramLink).toHaveBeenCalledWith("https://t.me/share/url?x");
  });
});
