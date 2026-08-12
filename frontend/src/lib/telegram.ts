interface TelegramWebApp {
  initData: string;
  initDataUnsafe: Record<string, unknown>;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  viewportHeight: number;
  isExpanded: boolean;
  platform: string;
  ready: () => void;
  expand: () => void;
  disableVerticalSwipes?: () => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  onEvent: (event: string, handler: () => void) => void;
  offEvent: (event: string, handler: () => void) => void;
  HapticFeedback?: {
    impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
    notificationOccurred: (type: "error" | "success" | "warning") => void;
    selectionChanged: () => void;
  };
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (cb: () => void) => void;
    offClick: (cb: () => void) => void;
  };
  openInvoice?: (url: string, callback?: (status: "paid" | "cancelled" | "failed" | "pending") => void) => void;
  openTelegramLink?: (url: string) => void;
  openLink?: (url: string, options?: { try_instant_view?: boolean }) => void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function isInsideTelegram(): boolean {
  const webApp = getTelegramWebApp();
  return Boolean(webApp?.initData);
}

export function getRawInitData(): string {
  return getTelegramWebApp()?.initData ?? "";
}

export function initTelegramApp(): void {
  const webApp = getTelegramWebApp();
  if (!webApp) return;
  webApp.ready();
  webApp.expand();
  webApp.disableVerticalSwipes?.();
}

export function getTelegramColorScheme(): "light" | "dark" {
  return getTelegramWebApp()?.colorScheme ?? "dark";
}

export function haptic(style: "light" | "medium" | "heavy" = "light"): void {
  getTelegramWebApp()?.HapticFeedback?.impactOccurred(style);
}

export function hapticNotify(type: "error" | "success" | "warning"): void {
  getTelegramWebApp()?.HapticFeedback?.notificationOccurred(type);
}

/** Opens a Telegram Stars (or other Bot Payments) invoice link natively
 * inside the Mini App. Resolves with the invoice status once the payment
 * sheet closes — `"paid"` only means Telegram accepted the payment, not that
 * the pack has been granted yet (that happens async once our bot relays the
 * `successful_payment` update to the backend), so callers should poll for
 * the actual result rather than trusting this status alone. */
export function openTelegramInvoice(url: string): Promise<"paid" | "cancelled" | "failed" | "pending"> {
  return new Promise((resolve) => {
    const webApp = getTelegramWebApp();
    if (!webApp?.openInvoice) {
      resolve("failed");
      return;
    }
    webApp.openInvoice(url, (status) => resolve(status));
  });
}

/** Opens a t.me link (chat/channel invite, etc.) through Telegram's own
 * handler when running inside the Mini App — `openTelegramLink` is what lets
 * Telegram switch straight to the chat instead of bouncing through an
 * in-app browser tab. Falls back to a plain new-tab open outside Telegram
 * (e.g. testing in a desktop browser via dev mode). */
export function openTelegramLink(url: string): void {
  const webApp = getTelegramWebApp();
  if (webApp?.openTelegramLink) {
    webApp.openTelegramLink(url);
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

/** Opens an arbitrary external URL (not a t.me link — use openTelegramLink
 * for those) in Telegram's in-app browser, with Instant View for pages that
 * support it (e.g. telegra.ph docs render natively instead of as a web
 * page). Falls back to a plain new-tab open outside Telegram. */
export function openLink(url: string): void {
  const webApp = getTelegramWebApp();
  if (webApp?.openLink) {
    webApp.openLink(url, { try_instant_view: true });
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}
