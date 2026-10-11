import { createMyPlayerStarsInvoice, fetchMyPlayerStarsInvoiceStatus } from "@/api/myPlayer";
import { openTelegramInvoice } from "@/lib/telegram";

/** Pays a «Мой игрок» purchase (extra training / «Имущество» item) with
 * Telegram Stars: invoice → native payment sheet → poll until the bot has
 * relayed the payment and the server delivered it. Resolves to "paid",
 * "cancelled" or throws with a user-facing message. */
export async function payMyPlayerWithStars(purchase: "training" | "item", itemId?: number): Promise<"paid" | "cancelled"> {
  const invoice = await createMyPlayerStarsInvoice(purchase, itemId);
  const status = await openTelegramInvoice(invoice.invoice_link);
  if (status === "cancelled") return "cancelled";
  if (status === "failed") throw new Error("Платёж не прошёл");
  for (let attempt = 0; attempt < 20; attempt++) {
    const result = await fetchMyPlayerStarsInvoiceStatus(invoice.payload_token);
    if (result.status === "completed") return "paid";
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Покупка ещё обрабатывается — загляни через минуту");
}
