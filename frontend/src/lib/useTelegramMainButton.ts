import { useEffect, useRef } from "react";

import { getTelegramWebApp, isInsideTelegram } from "@/lib/telegram";

/** Telegram's native bottom MainButton for a screen's primary action.
 * Returns true when it is in use — the screen then hides its own in-page
 * button so the action is not shown twice. Outside Telegram (browser dev
 * mode) it returns false and the page keeps its regular button. */
export function useTelegramMainButton({
  text,
  onClick,
  visible = true,
  enabled = true,
  loading = false,
}: {
  text: string;
  onClick: () => void;
  visible?: boolean;
  enabled?: boolean;
  loading?: boolean;
}): boolean {
  const button = isInsideTelegram() ? getTelegramWebApp()?.MainButton : undefined;
  // Latest handler without re-subscribing on every render.
  const handlerRef = useRef(onClick);
  handlerRef.current = onClick;

  useEffect(() => {
    if (!button) return;
    const handler = () => handlerRef.current();
    button.onClick(handler);
    return () => {
      button.offClick(handler);
      button.hideProgress();
      button.hide();
    };
  }, [button]);

  useEffect(() => {
    if (!button) return;
    if (!visible) {
      button.hide();
      return;
    }
    button.setText(text);
    if (enabled && !loading) button.enable();
    else button.disable();
    if (loading) button.showProgress(false);
    else button.hideProgress();
    button.show();
  }, [button, text, visible, enabled, loading]);

  return !!button;
}
