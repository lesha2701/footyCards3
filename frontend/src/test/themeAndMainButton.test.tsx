import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useTelegramMainButton } from "@/lib/useTelegramMainButton";
import { useUiStore } from "@/store/uiStore";

afterEach(() => {
  delete window.Telegram;
  localStorage.clear();
});

describe("theme preference", () => {
  it("applies an explicit choice and remembers it", () => {
    useUiStore.getState().setPreference("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("theme")).toBe("light");
    useUiStore.getState().setPreference("dark");
    expect(useUiStore.getState().theme).toBe("dark");
  });

  it("'auto' follows Telegram's color scheme and paints its header", () => {
    const setHeaderColor = vi.fn();
    window.Telegram = { WebApp: { initData: "x", colorScheme: "light", setHeaderColor } as never };
    useUiStore.getState().setPreference("auto");
    expect(useUiStore.getState().theme).toBe("light");
    expect(setHeaderColor).toHaveBeenCalledWith("#ffffff");
  });
});

describe("useTelegramMainButton", () => {
  it("is not used outside Telegram, so the page keeps its own button", () => {
    const { result } = renderHook(() => useTelegramMainButton({ text: "Играть", onClick: () => {} }));
    expect(result.current).toBe(false);
  });

  it("shows the native button with the text, disabled while not allowed", () => {
    const button = {
      setText: vi.fn(), show: vi.fn(), hide: vi.fn(), enable: vi.fn(), disable: vi.fn(),
      showProgress: vi.fn(), hideProgress: vi.fn(), onClick: vi.fn(), offClick: vi.fn(),
    };
    window.Telegram = { WebApp: { initData: "x", MainButton: button } as never };
    const { result, unmount } = renderHook(() =>
      useTelegramMainButton({ text: "Играть матч", onClick: () => {}, enabled: false }),
    );
    expect(result.current).toBe(true);
    expect(button.setText).toHaveBeenCalledWith("Играть матч");
    expect(button.disable).toHaveBeenCalled();
    expect(button.show).toHaveBeenCalled();
    unmount();
    expect(button.hide).toHaveBeenCalled();
    expect(button.offClick).toHaveBeenCalled();
  });
});
