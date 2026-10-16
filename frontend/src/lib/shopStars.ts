import { fetchShopInvoiceStatus } from "@/api/monetization";
import { openTelegramInvoice } from "@/lib/telegram";
import type { StarsInvoiceCreate } from "@/types";

/** Pays a monetization product (calendar catch-up, cosmetic, club pass,
 * season pass, starter offer) with Telegram Stars: invoice → native payment
 * sheet → poll until the bot relayed the payment and the server delivered
 * it. Resolves to "paid" or "cancelled"; throws with a user-facing message. */
export async function payShopWithStars(createInvoice: () => Promise<StarsInvoiceCreate>): Promise<"paid" | "cancelled"> {
  const invoice = await createInvoice();
  const status = await openTelegramInvoice(invoice.invoice_link);
  if (status === "cancelled") return "cancelled";
  if (status === "failed") throw new Error("Платёж не прошёл");
  for (let attempt = 0; attempt < 20; attempt++) {
    const result = await fetchShopInvoiceStatus(invoice.payload_token);
    if (result.status === "completed") return "paid";
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Покупка ещё обрабатывается — загляни через минуту");
}
