import { useState } from "react";

import { createStarsInvoice, fetchStarsInvoiceStatus } from "@/api/packs";
import { ApiRequestError } from "@/lib/api";
import { openTelegramInvoice } from "@/lib/telegram";
import type { PackOpenResult } from "@/types";

async function pollStarsInvoice(payloadToken: string): Promise<PackOpenResult> {
  const maxAttempts = 20;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const status = await fetchStarsInvoiceStatus(payloadToken);
    if (status.status === "completed" && status.result) return status.result;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Пак ещё не пришёл — проверь вкладку «Мои карточки» через минуту");
}

export type StarsPurchasePhase = "idle" | "invoicing" | "waiting" | "delivering" | "error";

export function useStarsPackPurchase(packId: number, onPurchased: (result: PackOpenResult) => void) {
  const [phase, setPhase] = useState<StarsPurchasePhase>("idle");
  const [error, setError] = useState<string | null>(null);

  const buy = async () => {
    setError(null);
    try {
      setPhase("invoicing");
      const invoice = await createStarsInvoice(packId);

      setPhase("waiting");
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") {
        setPhase("idle");
        return;
      }
      if (paymentStatus === "failed") {
        setPhase("error");
        setError("Платёж не прошёл");
        return;
      }

      // "paid" or "pending" — the pack itself is granted asynchronously once
      // our bot relays Telegram's successful_payment update to the backend.
      setPhase("delivering");
      const result = await pollStarsInvoice(invoice.payload_token);
      setPhase("idle");
      onPurchased(result);
    } catch (err) {
      setPhase("error");
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "Не удалось купить пак");
    }
  };

  return {
    phase,
    error,
    buy,
    busy: phase === "invoicing" || phase === "waiting" || phase === "delivering",
  };
}
