import { fetchProspect, fetchProspectInvoiceStatus, type ProspectView } from "@/api/prospect";
import { openTelegramInvoice } from "@/lib/telegram";
import type { StarsInvoiceCreate } from "@/types";

export const PROSPECT_KEY = ["prospect"];

// Backdrops of the prospect's card (cosmetics "bg_*").
export const BACKDROPS: Record<string, string> = {
  bg_yard: "from-emerald-900/60 via-bg-raised to-bg-surface",
  bg_gym: "from-sky-900/60 via-bg-raised to-bg-surface",
  bg_sunset: "from-orange-500/50 via-rose-900/40 to-bg-surface",
  bg_lights: "from-indigo-500/50 via-slate-900/60 to-bg-surface",
  bg_gold: "from-amber-400/60 via-amber-900/40 to-bg-surface",
  bg_snow: "from-sky-200/40 via-slate-800/60 to-bg-surface",
  bg_pumpkin: "from-orange-600/60 via-purple-950/60 to-bg-surface",
};

export const AGE_WORD = (n: number) =>
  n % 10 === 1 && n % 100 !== 11 ? "год" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "года" : "лет";
export const fmt = (n: number) => n.toLocaleString("ru-RU");
const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
export const roman = (n: number) => ROMAN[n] ?? String(n);

/** Opens a Stars invoice and waits for the bot to deliver it; null = cancelled. */
export async function payWithStars(create: () => Promise<StarsInvoiceCreate>): Promise<ProspectView | null> {
  const invoice = await create();
  const status = await openTelegramInvoice(invoice.invoice_link, invoice.payload_token);
  if (status === "cancelled") return null;
  if (status === "failed") throw new Error("Платёж не прошёл");
  for (let i = 0; i < 20; i++) {
    if ((await fetchProspectInvoiceStatus(invoice.payload_token)).status === "completed") return fetchProspect();
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("Оплата ещё обрабатывается — загляни через минуту");
}
