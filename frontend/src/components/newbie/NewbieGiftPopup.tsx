import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation } from "react-router-dom";

import { claimNewbieStep, fetchNewbie } from "@/api/newbie";
import { IconGift } from "@/components/icons";
import NewbiePopup from "@/components/newbie/NewbiePopup";
import { formatGameError } from "@/lib/errors";
import { RARITY_LABELS } from "@/lib/rarity";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { GrantedRewards } from "@/types";

const dismissKey = (day: number) => `fc_newbie_gift_later_${day}`;

function wasDismissed(day: number) {
  try {
    return sessionStorage.getItem(dismissKey(day)) === "1";
  } catch {
    return false;
  }
}

function describe(r: GrantedRewards): string {
  const parts: string[] = [];
  if (r.coins) parts.push(`+${r.coins.toLocaleString("ru-RU")} монет`);
  for (const c of r.cards) parts.push(`${c.player.display_name} (${RARITY_LABELS[c.player.rarity].toLowerCase()})`);
  return parts.join(", ");
}

/** The «Путь дебютанта» day-2 / day-3 gift as a popup on home: as a tile in
 * the path card most of the players who came back never claimed it. Waits
 * for the streak and comeback popups; «Позже» hides it for this visit. */
export default function NewbieGiftPopup() {
  const location = useLocation();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: state } = useQuery({ queryKey: ["newbie"], queryFn: fetchNewbie, staleTime: 60_000 });
  // The other login popups share these caches; ours waits until they are gone.
  const { data: streak } = useQuery<unknown[]>({ queryKey: ["streak-rewards"], queryFn: skipToken });
  const { data: comeback } = useQuery<unknown[]>({ queryKey: ["comeback-gifts"], queryFn: skipToken });
  const [hidden, setHidden] = useState(0);
  const [got, setGot] = useState<string | null>(null);

  const claim = useMutation({
    mutationFn: claimNewbieStep,
    onSuccess: (data) => {
      updateBalance(data.rewards.new_balance);
      hapticNotify("success");
      setGot(describe(data.rewards) || "Подарок получен");
      queryClient.setQueryData(["newbie"], data.state);
      queryClient.invalidateQueries({ queryKey: ["collection"] });
    },
  });

  if (got) {
    return <NewbiePopup open Icon={IconGift} kicker="Подарок получен" title={got} cta="Отлично" onCta={() => setGot(null)} />;
  }
  const gift = state?.active ? state.gifts.find((g) => g.ready && !g.claimed) : undefined;
  const otherPopup = !!streak?.length || !!comeback?.length;
  if (!gift || location.pathname !== "/" || otherPopup || hidden === gift.day || wasDismissed(gift.day)) return null;

  const what = gift.card_rarity ? `${RARITY_LABELS[gift.card_rarity].toLowerCase()} карта` : `${gift.coins.toLocaleString("ru-RU")} монет`;
  return (
    <NewbiePopup
      open
      Icon={IconGift}
      kicker={`Путь дебютанта · день ${gift.day}`}
      title="Ты вернулся — держи подарок"
      text={<>Сегодня тебя ждёт {what}.</>}
      cta="Забрать"
      onCta={() => claim.mutate(`day${gift.day}`)}
      busy={claim.isPending}
      error={claim.isError ? formatGameError(claim.error, "Не получилось") : null}
      secondary="Позже"
      onSecondary={() => {
        try {
          sessionStorage.setItem(dismissKey(gift.day), "1");
        } catch {
          /* private mode: hidden until the reload anyway */
        }
        setHidden(gift.day);
      }}
    />
  );
}
