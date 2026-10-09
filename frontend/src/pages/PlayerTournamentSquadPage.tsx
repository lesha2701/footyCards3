import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import CardPickerModal from "@/components/cards/CardPickerModal";
import CardSkillBadge from "@/components/cards/CardSkillBadge";
import { skillByCode, skillInactiveReason, useSkillCatalog } from "@/lib/cardSkills";
import UserCoachCardPickerModal from "@/components/cards/UserCoachCardPickerModal";
import UserStadiumCardPickerModal from "@/components/cards/UserStadiumCardPickerModal";
import { IconCheck, IconChevronLeft, IconPlus } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchCollection } from "@/api/collection";
import {
  activatePersonalSquad, fetchPersonalSquadCoachCards, fetchPersonalSquads, fetchPersonalSquadStadiumCards,
  renamePersonalSquad, setPersonalSquadCards, setPersonalSquadCoach, setPersonalSquadStadium, setPersonalSquadTactics,
} from "@/api/personalTournament";
import { staticUrl } from "@/lib/api";
import { BOOST_TYPE_LABELS } from "@/lib/coaches";
import { FORMATIONS, MENTALITIES, PLAYSTYLES } from "@/lib/clubTactics";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, type FormationSlot } from "@/lib/formation";
import { formatGameError } from "@/lib/errors";
import type { PersonalSquadSlot, UserCard } from "@/types";

export default function PlayerTournamentSquadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: templates, isLoading } = useQuery({ queryKey: ["player-tournament", "squads"], queryFn: fetchPersonalSquads });
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const activeIndex = templates?.find((t) => t.is_active)?.template_index ?? 1;
  const viewedIndex = selectedIndex ?? activeIndex;
  const squad = templates?.find((t) => t.template_index === viewedIndex);
  const { data: skillCatalog } = useSkillCatalog();
  const skillInactive = (code?: string | null, position?: string) =>
    skillInactiveReason(skillByCode(skillCatalog?.skills, code), "tournament", position, skillCatalog?.rules.enabled ?? true);
  const squadSkills = (squad?.slots ?? []).filter((s) => s.skill_code);
  const activeSquadSkills = squadSkills.filter((s) => !skillInactive(s.skill_code, s.player?.position));

  const [pickerSearch, setPickerSearch] = useState("");
  const { data: collectionPage } = useQuery({
    queryKey: ["collection-for-player-tournament", pickerSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: pickerSearch || undefined }),
  });
  const { data: coachCards } = useQuery({ queryKey: ["player-tournament", "coach-cards"], queryFn: fetchPersonalSquadCoachCards });
  const { data: stadiumCards } = useQuery({ queryKey: ["player-tournament", "stadium-cards"], queryFn: fetchPersonalSquadStadiumCards });

  const [pickerSlot, setPickerSlot] = useState<PersonalSquadSlot | null>(null);
  const [coachPickerOpen, setCoachPickerOpen] = useState(false);
  const [stadiumPickerOpen, setStadiumPickerOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setCardsMutation = useMutation({
    mutationFn: (slots: { slot_code: string; user_card_id: number }[]) => setPersonalSquadCards(viewedIndex, slots),
    onSuccess: () => { setError(null); queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); queryClient.invalidateQueries({ queryKey: ["player-tournament", "current"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось обновить состав")),
  });

  const setTacticsMutation = useMutation({
    mutationFn: (payload: { formation: string; mentality: string; playstyle: string }) => setPersonalSquadTactics(viewedIndex, payload),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); queryClient.invalidateQueries({ queryKey: ["player-tournament", "current"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось обновить тактику")),
  });

  const setCoachMutation = useMutation({
    mutationFn: (userCoachCardId: number | null) => setPersonalSquadCoach(viewedIndex, userCoachCardId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); setCoachPickerOpen(false); },
    onError: (err) => setError(formatGameError(err, "Не удалось назначить тренера")),
  });

  const setStadiumMutation = useMutation({
    mutationFn: (userStadiumCardId: number | null) => setPersonalSquadStadium(viewedIndex, userStadiumCardId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); setStadiumPickerOpen(false); },
    onError: (err) => setError(formatGameError(err, "Не удалось назначить стадион")),
  });

  const activateMutation = useMutation({
    mutationFn: () => activatePersonalSquad(viewedIndex),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); queryClient.invalidateQueries({ queryKey: ["player-tournament", "current"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось переключить шаблон")),
  });

  const [renamingTemplate, setRenamingTemplate] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const renameMutation = useMutation({
    mutationFn: (name: string) => renamePersonalSquad(viewedIndex, name),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); setRenamingTemplate(false); },
  });

  const updateTactics = (patch: Partial<{ formation: string; mentality: string; playstyle: string }>) => {
    if (!squad) return;
    setTacticsMutation.mutate({ formation: squad.formation, mentality: squad.mentality, playstyle: squad.playstyle, ...patch });
  };

  if (isLoading) return <ListSkeleton />;

  const usedPlayerIds = (pickerSlot
    ? squad?.slots.filter((s) => s.player && s.slot_code !== pickerSlot.slot_code)
    : squad?.slots.filter((s) => s.player)
  )?.map((s) => s.player!.id) ?? [];

  const cardsForSlot = (slot: PersonalSquadSlot): UserCard[] => {
    const positions = CATEGORY_POSITIONS[slot.category as FormationSlot["category"]];
    return (collectionPage?.items ?? []).filter((c) => positions.includes(c.player.position));
  };

  const assignSlot = async (slot: PersonalSquadSlot, card: UserCard) => {
    const currentSlots = (squad?.slots ?? [])
      .filter((s) => s.user_card_id != null && s.slot_code !== slot.slot_code)
      .map((s) => ({ slot_code: s.slot_code, user_card_id: s.user_card_id! }));
    currentSlots.push({ slot_code: slot.slot_code, user_card_id: card.id });
    try {
      await setCardsMutation.mutateAsync(currentSlots);
      setPickerSlot(null);
      setPickerSearch("");
    } catch {
      // Error is surfaced via setCardsMutation's onError; keep the picker
      // open so the player can choose a different card instead of it
      // silently closing.
    }
  };

  return (
    <div className="flex flex-col gap-4 pb-24">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/player-tournament")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Состав для турнира</h1>
      </div>

      <section className="flex gap-1.5 overflow-x-auto pb-1">
        {(templates ?? []).map((t) => (
          <button
            key={t.template_index}
            onClick={() => { setSelectedIndex(t.template_index); setRenamingTemplate(false); }}
            className={`flex shrink-0 flex-col items-center gap-0.5 rounded-xl px-3 py-1.5 ${
              t.template_index === viewedIndex ? "bg-accent-lime text-bg-base" : "bg-white/5 text-ink-mist"
            }`}
          >
            <span className="whitespace-nowrap text-[11px] font-bold">{t.name}</span>
            {t.is_active && (
              <span className={`text-[8px] ${t.template_index === viewedIndex ? "text-bg-base/70" : "text-accent-lime"}`}>
                Активный
              </span>
            )}
          </button>
        ))}
      </section>

      {renamingTemplate ? (
        <div className="flex gap-2">
          <input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            maxLength={64}
            className="flex-1 rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
            autoFocus
          />
          <button
            onClick={() => renameMutation.mutate(renameValue)}
            disabled={!renameValue.trim() || renameMutation.isPending}
            className="rounded-xl bg-accent-lime px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
          >
            Сохранить
          </button>
        </div>
      ) : (
        <button
          onClick={() => { setRenameValue(squad?.name ?? ""); setRenamingTemplate(true); }}
          className="self-start text-[11px] font-semibold text-ink-mist-dim underline underline-offset-2"
        >
          Переименовать «{squad?.name}»
        </button>
      )}

      {viewedIndex !== activeIndex && (
        <button
          onClick={() => activateMutation.mutate()}
          disabled={activateMutation.isPending}
          className="rounded-xl bg-accent-lime/10 px-3 py-2 text-center text-xs font-semibold text-accent-lime disabled:opacity-40"
        >
          {activateMutation.isPending ? "Переключаем..." : `Сделать «${squad?.name}» активным для турнира`}
        </button>
      )}

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="font-display text-base font-bold text-ink-chalk">Состав {squad?.formation}</p>
            {squadSkills.length > 0 && (
              <p className="text-[11px] text-ink-mist">
                Навыки: действуют {activeSquadSkills.length} из {squadSkills.length}
              </p>
            )}
          </div>
          {squad?.is_complete && (
            <span className="flex items-center gap-1 font-mono text-xs font-bold text-accent-cyan">
              <IconCheck size={14} />
              Заполнен
            </span>
          )}
        </div>

        <div className="mb-3 flex flex-col gap-1.5">
          <TacticSelect
            label="Схема"
            options={FORMATIONS}
            value={squad?.formation ?? "4-3-3"}
            disabled={!squad || setTacticsMutation.isPending}
            onChange={(value) => updateTactics({ formation: value })}
          />
          <TacticSelect
            label="Настрой"
            options={MENTALITIES}
            value={squad?.mentality ?? "BALANCED"}
            disabled={!squad || setTacticsMutation.isPending}
            onChange={(value) => updateTactics({ mentality: value })}
          />
          <TacticSelect
            label="Стиль игры"
            options={PLAYSTYLES}
            value={squad?.playstyle ?? "CENTRAL_PLAY"}
            disabled={!squad || setTacticsMutation.isPending}
            onChange={(value) => updateTactics({ playstyle: value })}
          />
        </div>

        <div className="relative flex flex-col gap-3 overflow-hidden rounded-2xl bg-gradient-to-b from-emerald-950/60 to-emerald-900/30 p-3">
          {(["FWD", "MID", "DEF", "GK"] as const).map((category) => (
            <div key={category} className="relative flex justify-evenly gap-2">
              {category === "GK" && (
                <button
                  onClick={() => setCoachPickerOpen(true)}
                  disabled={setCoachMutation.isPending}
                  className={`absolute left-0 top-0 flex min-w-0 max-w-[72px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 ${
                    setCoachMutation.isPending ? "opacity-60" : ""
                  }`}
                >
                  {squad?.coach ? (
                    <>
                      <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                        <img
                          src={staticUrl(squad.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                          alt="" className="h-full w-full object-cover" loading="lazy"
                        />
                      </div>
                      <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[8px] font-bold leading-none text-accent-cyan">Тренер</span>
                    </>
                  ) : (
                    <>
                      <IconPlus size={16} className="text-ink-mist-dim" />
                      <span className="text-[8px] text-ink-mist-dim">Тренер</span>
                    </>
                  )}
                </button>
              )}
              {category === "GK" && (
                <button
                  onClick={() => setStadiumPickerOpen(true)}
                  disabled={setStadiumMutation.isPending}
                  className={`absolute right-0 top-0 flex min-w-0 max-w-[72px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 ${
                    setStadiumMutation.isPending ? "opacity-60" : ""
                  }`}
                >
                  {squad?.stadium ? (
                    <>
                      <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                        <img
                          src={staticUrl(squad.stadium.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                          alt="" className="h-full w-full object-cover" loading="lazy"
                        />
                      </div>
                      <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[8px] font-bold leading-none text-accent-cyan">
                        +{Math.round(squad.stadium.boost_pct * 100)}%
                      </span>
                    </>
                  ) : (
                    <>
                      <IconPlus size={16} className="text-ink-mist-dim" />
                      <span className="text-[8px] text-ink-mist-dim">Стадион</span>
                    </>
                  )}
                </button>
              )}
              {squad?.slots
                .filter((slot) => slot.category === category)
                .map((slot) => (
                  <button
                    key={slot.slot_code}
                    onClick={() => setPickerSlot(slot)}
                    disabled={setCardsMutation.isPending}
                    className="flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 disabled:opacity-60"
                  >
                    {slot.player ? (
                      <>
                        <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                          <img
                            src={staticUrl(slot.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                            alt="" className="h-full w-full object-cover" loading="lazy"
                          />
                        </div>
                        <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[9px] font-bold leading-none text-accent-cyan">
                          {slot.player.position}
                        </span>
                        <span className="font-mono text-[9px] font-bold leading-none text-accent-lime">{slot.player.rating}</span>
                        <CardSkillBadge
                          code={slot.skill_code}
                          level={slot.skill_level}
                          inactiveReason={skillInactive(slot.skill_code, slot.player.position)}
                        />
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

        {squad?.coach && (
          <div className="mt-3 rounded-xl bg-white/5 px-3 py-2">
            <p className="text-xs font-semibold text-ink-chalk">{squad.coach.display_name}</p>
            <p className="mt-0.5 text-[11px] text-ink-mist">
              {squad.coach.boosts.map((b) => `${BOOST_TYPE_LABELS[b.boost_type]} +${b.magnitude}`).join(" · ")}
            </p>
          </div>
        )}
        {squad?.stadium && (
          <div className="mt-3 rounded-xl bg-white/5 px-3 py-2">
            <p className="text-xs font-semibold text-ink-chalk">{squad.stadium.display_name}</p>
            <p className="mt-0.5 text-[11px] text-ink-mist">+{Math.round(squad.stadium.boost_pct * 100)}% к силе</p>
          </div>
        )}
      </section>

      {pickerSlot && (
        <CardPickerModal
          showSkills
          open
          title={`Выбери на позицию ${CATEGORY_LABELS[pickerSlot.category as FormationSlot["category"]]}`}
          cards={cardsForSlot(pickerSlot)}
          disabledCardIds={cardsForSlot(pickerSlot).filter((c) => usedPlayerIds.includes(c.player.id)).map((c) => c.id)}
          onSelect={(card) => assignSlot(pickerSlot, card)}
          onClose={() => { setPickerSlot(null); setPickerSearch(""); }}
          searchValue={pickerSearch}
          onSearchChange={setPickerSearch}
        />
      )}

      <UserCoachCardPickerModal
        open={coachPickerOpen}
        cards={coachCards ?? []}
        onSelect={(card) => setCoachMutation.mutate(card ? card.id : null)}
        onClose={() => setCoachPickerOpen(false)}
      />

      <UserStadiumCardPickerModal
        open={stadiumPickerOpen}
        cards={stadiumCards ?? []}
        onSelect={(card) => setStadiumMutation.mutate(card ? card.id : null)}
        onClose={() => setStadiumPickerOpen(false)}
      />
    </div>
  );
}

function TacticSelect({
  label, options, value, disabled, onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const selected = options.find((o) => o.value === value);
  return (
    <div className={`relative flex items-center justify-between gap-3 rounded-xl bg-white/5 px-3 py-2.5 ${disabled ? "opacity-60" : ""}`}>
      <span className="shrink-0 text-[10px] uppercase tracking-wide text-ink-mist-dim">{label}</span>
      <span className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-sm font-semibold text-ink-chalk">{selected?.label ?? value}</span>
      </span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className="absolute inset-0 h-full w-full cursor-pointer appearance-none opacity-0 disabled:cursor-default"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </div>
  );
}
