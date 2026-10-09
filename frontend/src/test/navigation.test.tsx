import { act, render, renderHook, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import CardsSectionTabs from "@/components/layout/CardsSectionTabs";
import { usePersistentState } from "@/lib/usePersistentState";
import { useTelegramBackButton } from "@/lib/useTelegramBackButton";

describe("CardsSectionTabs", () => {
  const renderAt = (url: string) =>
    render(
      <MemoryRouter initialEntries={[url]}>
        <CardsSectionTabs />
      </MemoryRouter>,
    );
  const current = () => screen.getByRole("link", { current: "page" }).textContent;

  it("marks the screen of the cards section that is open", () => {
    renderAt("/collection");
    expect(current()).toBe("Альбом");
  });

  it("knows the ?tab=mine screen", () => {
    renderAt("/collection?tab=mine");
    expect(current()).toBe("Мои");
  });

  it("treats a trade detail page as the Обмены tab", () => {
    renderAt("/trades/42");
    expect(current()).toBe("Обмены");
  });
});

describe("usePersistentState", () => {
  afterEach(() => localStorage.clear());

  it("restores the last saved value", () => {
    const first = renderHook(() => usePersistentState("test.sort", "date"));
    act(() => first.result.current[1]("rating"));
    first.unmount();
    const second = renderHook(() => usePersistentState("test.sort", "date"));
    expect(second.result.current[0]).toBe("rating");
  });
});

describe("useTelegramBackButton", () => {
  afterEach(() => {
    delete window.Telegram;
  });

  function setup(url: string) {
    let clickHandler: (() => void) | null = null;
    const backButton = {
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn((cb: () => void) => { clickHandler = cb; }),
      offClick: vi.fn(),
    };
    window.Telegram = { WebApp: { BackButton: backButton } as never };
    let path = "";
    function Probe() {
      useTelegramBackButton();
      path = useLocation().pathname;
      return null;
    }
    render(
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="*" element={<Probe />} />
        </Routes>
      </MemoryRouter>,
    );
    return { backButton, click: () => act(() => clickHandler?.()), path: () => path };
  }

  it("is hidden on bottom-nav roots", () => {
    const { backButton } = setup("/play");
    expect(backButton.hide).toHaveBeenCalled();
    expect(backButton.show).not.toHaveBeenCalled();
  });

  it("goes to the section root when opened directly on an inner screen", () => {
    const { backButton, click, path } = setup("/trades/7");
    expect(backButton.show).toHaveBeenCalled();
    click();
    expect(path()).toBe("/collection");
  });
});
