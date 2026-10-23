import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AdminAntifraudPage from "@/admin/pages/AdminAntifraudPage";
import type { AntifraudScan } from "@/admin/types";

const account = (id: number, over: object = {}) => ({
  id, username: `u${id}`, telegram_id: 1000 + id, balance: 10, registered: "2026-09-19T12:00:00Z",
  last_seen: null, is_banned: false, stars_paid: 0, ...over,
});

const scan: AntifraudScan = {
  min_senders: 20, days: 120, burst_min: 30,
  hubs: [{ ...account(1, { username: "hubboss" }), senders: 238, coins_in: 2_162_516, coins_out: 2_118_943 }],
  hubs_summary: { total: 1, not_banned: 1, not_banned_unpaid: 1, coins: 2_162_516 },
  farms: [
    { ...account(2), coins_sent: 9000, hubs: 1, is_hub: false },
    { ...account(3, { stars_paid: 50, username: "payer" }), coins_sent: 100, hubs: 1, is_hub: false },
    { ...account(4, { is_banned: true }), coins_sent: 500, hubs: 1, is_hub: false },
  ],
  farms_summary: { total: 3, not_banned: 2, not_banned_unpaid: 1, coins: 9600 },
  bursts: [{ hour: "2026-09-19T12:00:00Z", registered: 238, farm_accounts: 238 }],
};

const banMock = vi.fn(async (ids: number[]) => ({ banned: ids.length, user_ids: ids }));
vi.mock("@/admin/api", () => ({
  fetchAntifraudScan: async () => scan,
  banAntifraudUsers: (ids: number[]) => banMock(ids),
}));

describe("admin antifraud", () => {
  it("shows the network and bans farms without touching payers or the banned", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<QueryClientProvider client={new QueryClient()}><AdminAntifraudPage /></QueryClientProvider>);

    expect(await screen.findByText(/@hubboss/)).toBeInTheDocument();
    expect(screen.getByText("Забанить сборщиков (1)")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Забанить фарм-аккаунты (1)"));
    await waitFor(() => expect(banMock).toHaveBeenCalledWith([2]));
  });
});
