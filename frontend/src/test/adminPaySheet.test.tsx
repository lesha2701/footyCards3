import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminPaySheet from "@/components/common/AdminPaySheet";
import { openTelegramInvoice } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { UserMe } from "@/types";

const freeStarsDelivery = vi.fn();
vi.mock("@/api/adminStars", () => ({ freeStarsDelivery: (...a: unknown[]) => freeStarsDelivery(...a) }));

describe("AdminPaySheet", () => {
  beforeEach(() => {
    freeStarsDelivery.mockReset();
    useAuthStore.setState({ user: { id: 1, is_admin: true } as UserMe });
  });

  it("lets an admin take a Stars purchase free, and resolves it as paid", async () => {
    freeStarsDelivery.mockResolvedValue({ recipient_id: 1, recipient_name: "Я", stars: 99 });
    render(<AdminPaySheet />);
    let status: string | undefined;
    act(() => { void openTelegramInvoice("https://t.me/invoice/x", "tok1").then((s) => { status = s; }); });
    fireEvent.click(await screen.findByRole("button", { name: "Получить бесплатно" }));
    await waitFor(() => expect(status).toBe("paid"));
    expect(freeStarsDelivery).toHaveBeenCalledWith("tok1", null);
  });

  it("gifts it to the named player", async () => {
    freeStarsDelivery.mockResolvedValue({ recipient_id: 7, recipient_name: "Коля", stars: 49 });
    render(<AdminPaySheet />);
    let status: string | undefined;
    act(() => { void openTelegramInvoice("https://t.me/invoice/x", "tok2").then((s) => { status = s; }); });
    fireEvent.click(await screen.findByRole("button", { name: /Подарить$/ }));
    fireEvent.click(screen.getByRole("button", { name: "Подарить бесплатно" }));
    expect(await screen.findByText("Укажи игрока")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/username/), { target: { value: "@kolya" } });
    fireEvent.click(screen.getByRole("button", { name: "Подарить бесплатно" }));
    expect(await screen.findByText(/Подарено: Коля/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Готово" }));
    await waitFor(() => expect(status).toBe("cancelled"));
    expect(freeStarsDelivery).toHaveBeenCalledWith("tok2", "@kolya");
  });

  it("doesn't stop a regular player", async () => {
    useAuthStore.setState({ user: { id: 2, is_admin: false } as UserMe });
    render(<AdminPaySheet />);
    expect(await openTelegramInvoice("https://t.me/invoice/x", "tok3")).toBe("failed"); // no Telegram here
    expect(screen.queryByTestId("admin-pay-sheet")).toBeNull();
  });
});
