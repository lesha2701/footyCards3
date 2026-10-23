import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import StarsPaymentsSection from "@/admin/components/StarsPaymentsSection";
import type { StarsPaymentReceipt } from "@/admin/types";

const failed: StarsPaymentReceipt = {
  id: 11, telegram_payment_charge_id: "ch-1", telegram_user_id: 555, user_id: 3, user_username: "fan",
  user_display_name: "Игрок", product: "Пак «Звёздный»", stars_amount: 50, status: "failed", attempts: 8,
  last_error: "Gift set not found", next_attempt_at: null, auto_retry: false,
  created_at: "2026-10-16T10:00:00Z", delivered_at: null, refunded_at: null,
};

const fetchMock = vi.fn(async (status: string) => ({
  items: status === "problems" ? [failed] : [], total: status === "problems" ? 1 : 0, page: 1, page_size: 50, pages: 1,
}));
const retryMock = vi.fn(async (id: number) => ({ ...failed, id, status: "delivered" }));
const refundMock = vi.fn(async (id: number) => ({ ...failed, id, status: "refunded" }));

vi.mock("@/admin/api", () => ({
  fetchStarsReceipts: (status: string) => fetchMock(status),
  retryStarsReceipt: (id: number) => retryMock(id),
  refundStarsReceipt: (id: number) => refundMock(id),
}));

function renderSection() {
  render(<QueryClientProvider client={new QueryClient()}><StarsPaymentsSection /></QueryClientProvider>);
}

describe("admin Stars payments", () => {
  it("shows an undelivered payment with its error and lets the admin deliver it", async () => {
    renderSection();
    expect(await screen.findByText(/Пак «Звёздный»/)).toBeInTheDocument();
    expect(screen.getByText("Ошибка начисления")).toBeInTheDocument();
    expect(screen.getByText(/Gift set not found/)).toBeInTheDocument();
    expect(screen.getByText(/автоповторы закончились/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Начислить"));
    await waitFor(() => expect(retryMock).toHaveBeenCalledWith(11));
  });

  it("asks before returning the Stars", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderSection();
    fireEvent.click(await screen.findByText("Вернуть звёзды"));
    expect(refundMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Вернуть звёзды"));
    await waitFor(() => expect(refundMock).toHaveBeenCalledWith(11));
    expect(confirmSpy).toHaveBeenCalledTimes(2);
  });

  it("says when every payment is delivered", async () => {
    fetchMock.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 50, pages: 1 });
    renderSection();
    expect(await screen.findByText(/Все оплаты начислены/)).toBeInTheDocument();
  });
});
