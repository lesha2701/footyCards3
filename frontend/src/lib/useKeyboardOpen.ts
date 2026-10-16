import { useEffect, useState } from "react";

const NON_TEXT_INPUTS = new Set(["checkbox", "radio", "range", "button", "submit", "reset", "color", "file", "image"]);

function isTextField(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable || el.tagName === "TEXTAREA") return true;
  return el.tagName === "INPUT" && !NON_TEXT_INPUTS.has((el as HTMLInputElement).type);
}

/** True while a text field has focus — i.e. the on-screen keyboard is (about
 * to be) up on a phone. Used to get fixed bottom UI out of the way: in the
 * Telegram WebView a fixed bottom bar otherwise rides up on top of the
 * keyboard and covers the field being typed into. Focus is a reliable
 * signal in and out of Telegram, unlike viewport-height heuristics. */
export function useKeyboardOpen(): boolean {
  const [open, setOpen] = useState(() => isTextField(document.activeElement));

  useEffect(() => {
    const onFocusIn = (e: FocusEvent) => {
      if (isTextField(e.target)) setOpen(true);
    };
    // focusout fires before focus lands on the next element: check on the
    // next tick so moving between two fields doesn't flash the bar.
    const onFocusOut = () => {
      window.setTimeout(() => setOpen(isTextField(document.activeElement)), 0);
    };
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    return () => {
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
    };
  }, []);

  return open;
}
