import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import ClubCardPickerModal from "@/components/clubs/ClubCardPickerModal";
import { IconChevronLeft, IconPlus } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchClubCards, fetchClubLineup, setClubLineup } from "@/api/clubSquad";
import { staticUrl } from "@/lib/api";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, type FormationSlot } from "@/lib/formation";
import { formatGameError } from "@/lib/errors";
import type { ClubCard, ClubLineupSlot } from "@/types";

export default function ClubSquadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: lineup, isLoading: lineupLoading } = useQuery({ queryKey: ["clubs", "lineup"], queryFn: fetchClubLineup });
  const { data: cards } = useQuery({ queryKey: ["clubs", "cards"], queryFn: fetchClubCards });
  const [pickerSlot, setPickerSlot] = useState<ClubLineupSlot | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setLineupMutation = useMutation({
    mutationFn: setClubLineup,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "lineup"] }); queryClient.invalidateQueries({ queryKey: ["clubs", "cards"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось обновить состав")),
  });

  if (lineupLoading) return <ListSkeleton />;

  const usedPlayerIds = (pickerSlot
    ? lineup?.slots.filter((s) => s.card && s.slot_code !== pickerSlot.slot_code)
    : lineup?.slots.filter((s) => s.card)
  )?.map((s) => s.card!.player.id) ?? [];

  const cardsForSlot = (slot: ClubLineupSlot): ClubCard[] => {
    const positions = CATEGORY_POSITIONS[slot.category as FormationSlot["category"]];
    return (cards ?? []).filter((c) => positions.includes(c.player.position));
  };

  const assignSlot = async (slot: ClubLineupSlot, card: ClubCard) => {
    const currentSlots = (lineup?.slots ?? [])
      .filter((s) => s.card && s.slot_code !== slot.slot_code)
      .map((s) => ({ slot_code: s.slot_code, club_card_id: s.card!.id }));
    currentSlots.push({ slot_code: slot.slot_code, club_card_id: card.id });
    await setLineupMutation.mutateAsync(currentSlots);
    setPickerSlot(null);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Состав клуба</h1>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-base font-bold text-ink-chalk">Состав 4-3-3</p>
          {lineup?.is_complete && <span className="font-mono text-sm font-bold text-accent-cyan">Сила: {lineup.team_strength}</span>}
        </div>
        <div className="relative flex flex-col gap-3 overflow-hidden rounded-2xl bg-gradient-to-b from-emerald-950/60 to-emerald-900/30 p-3">
          {(["FWD", "MID", "DEF", "GK"] as const).map((category) => (
            <div key={category} className="relative flex justify-evenly gap-2">
              {lineup?.slots
                .filter((slot) => slot.category === category)
                .map((slot) => (
                  <button
                    key={slot.slot_code}
                    onClick={() => setPickerSlot(slot)}
                    disabled={setLineupMutation.isPending}
                    className="flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 disabled:opacity-60"
                  >
                    {slot.card ? (
                      <>
                        <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                          <img
                            src={staticUrl(slot.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                            alt="" className="h-full w-full object-cover" loading="lazy"
                          />
                        </div>
                        <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[9px] font-bold leading-none text-accent-cyan">{slot.card.player.position}</span>
                        <span className="font-mono text-[9px] font-bold leading-none text-accent-lime">{slot.card.player.rating}</span>
                      </>
                    ) : (
                      <>
                        <IconPlus size={18} className="text-ink-mist-dim" />
                        <span className="text-[9px] text-ink-mist-dim">{CATEGORY_LABELS[slot.category as FormationSlot["category"]]}</span>
                      </>
                    )}
                  </button>
                ))}
            </div>
          ))}
        </div>
      </section>

      <div>
        <p className="mb-2 font-display text-sm font-bold text-ink-chalk">Запас</p>
        <div className="grid grid-cols-4 gap-2">
          {(cards ?? []).filter((c) => !c.is_in_lineup).map((c) => (
            <div key={c.id} className="flex flex-col items-center gap-1 rounded-xl bg-bg-surface p-1.5">
              <img
                src={staticUrl(c.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt="" className="aspect-square w-full rounded-lg object-cover"
              />
              <span className="font-mono text-[9px] text-ink-mist-dim">{c.player.position} · {c.player.rating}</span>
            </div>
          ))}
        </div>
      </div>

      {pickerSlot && (
        <ClubCardPickerModal
          open
          title={`Выбери на позицию ${CATEGORY_LABELS[pickerSlot.category as FormationSlot["category"]]}`}
          cards={cardsForSlot(pickerSlot)}
          disabledCardIds={cardsForSlot(pickerSlot).filter((c) => usedPlayerIds.includes(c.player.id)).map((c) => c.id)}
          onSelect={(card) => assignSlot(pickerSlot, card)}
          onClose={() => setPickerSlot(null)}
        />
      )}
    </div>
  );
}
