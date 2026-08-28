import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import ClubCardPickerModal from "@/components/clubs/ClubCardPickerModal";
import { IconChevronLeft, IconChevronUp, IconPlus, IconStar, IconTarget, IconUsers } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchMyClub } from "@/api/clubs";
import { fetchClubCards, fetchClubLineup, setClubLineup } from "@/api/clubSquad";
import { staticUrl } from "@/lib/api";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, type FormationSlot } from "@/lib/formation";
import { formatGameError } from "@/lib/errors";
import type { ClubCard, ClubLineupSlot } from "@/types";

export default function ClubSquadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: club } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });
  const { data: lineup, isLoading: lineupLoading } = useQuery({ queryKey: ["clubs", "lineup"], queryFn: fetchClubLineup });
  const { data: cards } = useQuery({ queryKey: ["clubs", "cards"], queryFn: fetchClubCards });
  const [pickerSlot, setPickerSlot] = useState<ClubLineupSlot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const canEdit = club?.my_role === "captain" || club?.my_role === "assistant";

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

      {!canEdit && club && (
        <p className="rounded-lg bg-white/5 px-3 py-2 text-xs text-ink-mist-dim">
          Менять состав могут только капитан и ассистенты.
        </p>
      )}

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
                    onClick={canEdit ? () => setPickerSlot(slot) : undefined}
                    disabled={!canEdit || setLineupMutation.isPending}
                    className={`flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm ${
                      canEdit ? "active:scale-95" : ""
                    } ${setLineupMutation.isPending ? "opacity-60" : ""}`}
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
                        {canEdit ? (
                          <IconPlus size={18} className="text-ink-mist-dim" />
                        ) : (
                          <span className="flex h-[18px] items-center text-ink-mist-dim">—</span>
                        )}
                        <span className="text-[9px] text-ink-mist-dim">{CATEGORY_LABELS[slot.category as FormationSlot["category"]]}</span>
                      </>
                    )}
                  </button>
                ))}
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <button
          onClick={() => setRulesOpen((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <span className="font-display text-sm font-bold text-ink-chalk">За что начисляется сила состава</span>
          <IconChevronUp
            size={16}
            className={`shrink-0 text-ink-mist-dim transition-transform ${rulesOpen ? "" : "rotate-180"}`}
          />
        </button>

        {rulesOpen && (
          <div className="mt-4 flex flex-col gap-3">
            <div className="flex gap-3 rounded-xl bg-white/5 p-3">
              <IconTarget size={18} className="mt-0.5 shrink-0 text-accent-lime" />
              <div>
                <p className="text-sm font-semibold text-ink-chalk">Позиция игрока</p>
                <p className="mt-0.5 text-xs text-ink-mist">
                  Игрок на своей родной позиции даёт <b className="text-ink-chalk">100%</b> рейтинга. В пределах своей
                  линии (например, защитник на другой защитной позиции) — <b className="text-ink-chalk">90%</b>.
                  Не в своей линии — только <b className="text-ink-chalk">75%</b>.
                </p>
              </div>
            </div>

            <div className="flex gap-3 rounded-xl bg-white/5 p-3">
              <IconStar size={18} className="mt-0.5 shrink-0 text-accent-lime" />
              <div>
                <p className="text-sm font-semibold text-ink-chalk">Редкость карточки</p>
                <p className="mt-0.5 text-xs text-ink-mist">
                  Каждая ступень редкости добавляет бонус к рейтингу карточки: обычная — без бонуса, редкая{" "}
                  <b className="text-ink-chalk">+3%</b>, эпическая <b className="text-ink-chalk">+6%</b>, легендарная{" "}
                  <b className="text-ink-chalk">+9%</b>.
                </p>
              </div>
            </div>

            <div className="flex gap-3 rounded-xl bg-white/5 p-3">
              <IconUsers size={18} className="mt-0.5 shrink-0 text-accent-lime" />
              <div>
                <p className="text-sm font-semibold text-ink-chalk">Химия состава</p>
                <p className="mt-0.5 text-xs text-ink-mist">
                  Собери в составе игроков одного клуба или одной сборной: за каждого игрока сверх первого из самой
                  многочисленной клубной группы — <b className="text-ink-chalk">+2</b> к силе состава, из самой
                  многочисленной страны — <b className="text-ink-chalk">+1</b>.
                </p>
              </div>
            </div>
          </div>
        )}
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
