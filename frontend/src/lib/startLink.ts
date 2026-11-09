import { getTelegramWebApp } from "@/lib/telegram";

/** Targets of an ad link: t.me/<bot>?startapp=penalty_vans opens the penalty
 * shootout, and "penalty_vans" is stored as where the player came from. The
 * label is free; only its first word can pick a target. */
const TARGETS: Record<string, string> = { penalty: "/play/penalty/3d" };

export function parseStartLink(param: string | null | undefined): { source?: string; path?: string } {
  if (!param || !/^[A-Za-z0-9_-]{1,64}$/.test(param)) return {};
  return { source: param, path: TARGETS[param.split("_")[0]] };
}

/** Telegram's start_param for a direct link, or ?src= when the app was opened
 * from the bot's button (bot/handlers/user.py). */
function readStartParam(): string | null {
  const param = getTelegramWebApp()?.initDataUnsafe?.start_param;
  if (typeof param === "string" && param) return param;
  return new URLSearchParams(window.location.search).get("src");
}

let link: ReturnType<typeof parseStartLink> | null = null;

export function startLink() {
  link ??= parseStartLink(readStartParam());
  return link;
}

/** The link's page, once: a later return to the home screen stays there. */
export function takeStartPath(): string | undefined {
  const { path } = startLink();
  if (path) link = { ...link, path: undefined };
  return path;
}
