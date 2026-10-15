import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TransactionsTable from "@/admin/components/TransactionsTable";

const fetchMock = vi.fn(async (params: { page: number }) => ({
  items: [{
    id: params.page, amount: params.page === 1 ? 50 : -20, balance_before: 0, balance_after: 100, type: "match_reward",
    description: `Матч стр. ${params.page}`, related_object_type: null, related_object_id: null,
    created_at: "2026-10-15T10:00:00Z", user_id: 7, user_name: "Игрок", username: "player", telegram_id: 123,
  }],
  total: 120, page: params.page, page_size: 50, pages: 3, income: 5000, spent: 1200,
}));

vi.mock("@/admin/api", () => ({ fetchAdminTransactions: (p: { page: number }) => fetchMock(p) }));

describe("admin transactions", () => {
  it("shows totals and pages through all transactions", async () => {
    render(<QueryClientProvider client={new QueryClient()}><TransactionsTable /></QueryClientProvider>);
    expect(await screen.findByText("Матч стр. 1")).toBeInTheDocument();
    expect(screen.getByText(/Найдено:/)).toHaveTextContent("120");
    // The page switcher is shown above and below the table.
    expect(screen.getAllByText("Вперёд")).toHaveLength(2);
    fireEvent.click(screen.getAllByText("Вперёд")[0]);
    expect(await screen.findByText("Матч стр. 2")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, page_size: 50 }));
  });
});
