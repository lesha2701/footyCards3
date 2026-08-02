import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { bulkSellCards, sellCard, setCardHiddenFromTrade } from "@/api/collection";
import { ApiRequestError } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { UserCard } from "@/types";

/** Shared sell/hide-from-trade/upgrade card-detail flow, reused by both the
 * flat "Мои карточки" grid and the album's owned-slot detail modal. */
export function useCardActions(invalidateKeys: string[][]) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [detailCard, setDetailCard] = useState<UserCard | null>(null);
  const [confirmSell, setConfirmSell] = useState<{ ids: number[]; lastCopy: boolean } | null>(null);
  const [upgradeCard, setUpgradeCard] = useState<UserCard | null>(null);

  const invalidate = () => invalidateKeys.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));

  const sellMutation = useMutation({
    mutationFn: ({ ids, confirmLastCopy }: { ids: number[]; confirmLastCopy: boolean }) =>
      ids.length === 1 ? sellCard(ids[0], confirmLastCopy) : bulkSellCards(ids, confirmLastCopy),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      invalidate();
      setDetailCard(null);
      setConfirmSell(null);
    },
    onError: (err: unknown) => {
      if (err instanceof ApiRequestError && err.details?.requires_confirmation) {
        setConfirmSell((prev) => (prev ? { ...prev, lastCopy: true } : null));
      }
    },
  });

  const hideMutation = useMutation({
    mutationFn: ({ id, hidden }: { id: number; hidden: boolean }) => setCardHiddenFromTrade(id, hidden),
    onSuccess: (updated) => {
      invalidate();
      setDetailCard((prev) => (prev && prev.id === updated.id ? updated : prev));
    },
  });

  return {
    detailCard, setDetailCard,
    confirmSell, setConfirmSell,
    upgradeCard, setUpgradeCard,
    sellMutation, hideMutation,
  };
}
