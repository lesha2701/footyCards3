import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { getTelegramWebApp } from "@/lib/telegram";
import { useMatchGuardStore } from "@/store/matchGuardStore";

// Bottom-nav roots: no native back button there, Telegram shows "Закрыть".
const ROOTS = new Set(["/", "/packs", "/play", "/collection", "/profile"]);
const isRoot = (pathname: string) => ROOTS.has(pathname) || pathname.startsWith("/admin");

/** Fallback when the screen was opened directly (deep link / reload) and
 * there is no in-app history to go back to: the section it belongs to. */
function parentOf(pathname: string): string {
  if (pathname.startsWith("/trades") || pathname.startsWith("/upgrade")) return "/collection";
  if (pathname.startsWith("/play") || pathname.startsWith("/player-tournament")) return "/play";
  if (pathname.startsWith("/packs")) return "/packs";
  return "/";
}

/** Telegram's native header BackButton on every inner screen, so players
 * can go back the way every Mini App works instead of hunting for a
 * "Назад" link. A live match keeps its guard: back asks before forfeiting. */
export function useTelegramBackButton() {
  const { pathname } = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const backButton = getTelegramWebApp()?.BackButton;
    if (!backButton) return;
    if (isRoot(pathname)) {
      backButton.hide();
      return;
    }
    const onBack = () => {
      const guard = useMatchGuardStore.getState();
      if (guard.active) {
        guard.requestNavigate(parentOf(pathname));
        return;
      }
      const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
      if (idx > 0) navigate(-1);
      else navigate(parentOf(pathname), { replace: true });
    };
    backButton.show();
    backButton.onClick(onBack);
    return () => backButton.offClick(onBack);
  }, [pathname, navigate]);
}
