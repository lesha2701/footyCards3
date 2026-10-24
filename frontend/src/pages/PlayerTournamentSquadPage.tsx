import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useRef, useState } from "react";

import CardPickerModal from "@/components/cards/CardPickerModal";
import PitchCardTile from "@/components/cards/PitchCardTile";
import { skillByCode, skillInactiveReason, useSkillCatalog } from "@/lib/cardSkills";
import UserCoachCardPickerModal from "@/components/cards/UserCoachCardPickerModal";
import UserStadiumCardPickerModal from "@/components/cards/UserStadiumCardPickerModal";
import { IconCheck, IconChevronLeft, IconPlus } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchCollection } from "@/api/collection";
import type { BenchUpgrade } from "@/api/lineups";
import BenchUpgradeHints from "@/components/squad/BenchUpgradeHints";
import { ChemistryDiamonds, ChemistryFrozenNote, ChemistryHints, ChemistryLinksOverlay, ChemistrySummary } from "@/components/squad/Chemistry";
import { chemistryGain, chemistrySwapHints, type ChemistrySwapHint } from "@/lib/chemistry";
import {
  activatePersonalSquad, autoFillPersonalSquad, fetchPersonalSquadBenchUpgrades, fetchPersonalSquadCoachCards, fetchPersonalSquads, fetchPersonalSquadStadiumCards,
  fetchPersonalTournamentTactics,
  renamePersonalSquad, setPersonalSquadCards, setPersonalSquadCoach, setPersonalSquadStadium, setPersonalSquadTactics,
} from "@/api/personalTournament";
import { staticUrl } from "@/lib/api";
import { BOOST_TYPE_LABELS } from "@/lib/coaches";
import type { ManagerStyle } from "@/api/manager";
import TacticsPanel from "@/components/manager/TacticsPanel";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, type FormationSlot } from "@/lib/formation";
import { inRow, pitchRows, PITCH_STYLE } from "@/lib/formationLayout";
import PitchBackground from "@/components/squad/PitchBackground";
import { formatGameError } from "@/lib/errors";
import { haptic } from "@/lib/telegram";
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
  const { data: tactics } = useQuery({ queryKey: ["player-tournament", "tactics"], queryFn: fetchPersonalTournamentTactics });
  const { data: stadiumCards } = useQuery({ queryKey: ["player-tournament", "stadium-cards"], queryFn: fetchPersonalSquadStadiumCards });

  const [pickerSlot, setPickerSlot] = useState<PersonalSquadSlot | null>(null);
  const [coachPickerOpen, setCoachPickerOpen] = useState(false);
  const [stadiumPickerOpen, setStadiumPickerOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pitchRef = useRef<HTMLDivElement>(null);

  const autoFillMutation = useMutation({
    mutationFn: (copyFromArena: boolean) => autoFillPersonalSquad(viewedIndex, copyFromArena),
    onSuccess: () => {
      haptic("medium");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] });
      queryClient.invalidateQueries({ queryKey: ["player-tournament", "current"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось собрать состав")),
  });

  const setCardsMutation = useMutation({
    mutationFn: (slots: { slot_code: string; user_card_id: number }[]) => setPersonalSquadCards(viewedIndex, slots),
    onSuccess: () => { setError(null); queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); queryClient.invalidateQueries({ queryKey: ["player-tournament", "current"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось обновить состав")),
  });

  const setTacticsMutation = useMutation({
    mutationFn: (payload: { formation: string; style: ManagerStyle }) => setPersonalSquadTactics(viewedIndex, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] });
      queryClient.invalidateQueries({ queryKey: ["player-tournament", "current"] });
      queryClient.invalidateQueries({ queryKey: ["player-tournament", "tactics"] });
    },
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

  const updateTactics = (patch: { formation?: string; style?: ManagerStyle }) => {
    if (!squad) return;
    setTacticsMutation.mutate({ formation: squad.formation, style: squad.style, ...patch });
  };

  const { data: benchUpgrades } = useQuery({
    queryKey: ["player-tournament", "squads", "bench", viewedIndex],
    queryFn: () => fetchPersonalSquadBenchUpgrades(viewedIndex),
    enabled: !!squad,
  });
  const applyBenchUpgrade = (hint: BenchUpgrade) => {
    const slots = (squad?.slots ?? [])
      .filter((s) => s.user_card_id != null && s.slot_code !== hint.slot_code)
      .map((s) => ({ slot_code: s.slot_code, user_card_id: s.user_card_id! }));
    slots.push({ slot_code: hint.slot_code, user_card_id: hint.suggested_card_id });
    setCardsMutation.mutate(slots);
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

  // Neighbour-link chemistry, see ArenaPage for the same wiring.
  const chemistry = squad?.chemistry;
  const chemistryOn = !!chemistry?.enabled;
  const chemBySlot = new Map((chemistry?.players ?? []).map((p) => [p.slot_code, p]));
  const chemSlots = squad?.slots ?? [];
  const chemistryHints = chemistryOn
    ? chemistrySwapHints(chemistry, chemSlots, (slot) =>
        cardsForSlot(slot as PersonalSquadSlot).map((c) => ({
          cardId: c.id, playerId: c.player.id, name: c.player.display_name, club: c.player.club, country: c.player.country, position: c.player.position,
        })),
      )
    : [];
  const applyChemistryHint = (hint: ChemistrySwapHint) => {
    const slots = (squad?.slots ?? [])
      .filter((s) => s.user_card_id != null && s.slot_code !== hint.slotCode)
      .map((s) => ({ slot_code: s.slot_code, user_card_id: s.user_card_id! }));
    slots.push({ slot_code: hint.slotCode, user_card_id: hint.cardId });
    setCardsMutation.mutate(slots);
  };
  const pickerChemistryNote = (card: UserCard) => {
    if (!pickerSlot) return null;
    const fit = slotFitPct(card.player.position, pickerSlot);
    const gain = chemistryOn ? chemistryGain(chemistry, chemSlots, pickerSlot.slot_code, card.player) : null;
    if (fit === 100 && gain == null) return null;
    return (
      <span className="flex items-center gap-1.5">
        {fit < 100 && <span className="font-mono text-micro font-bold text-red-400">−{100 - fit}% не своя позиция</span>}
        {gain != null && (
          <span className={`font-mono text-micro font-bold ${gain > 0 ? "text-accent-green" : gain < 0 ? "text-red-400" : "text-ink-mist-dim"}`}>
            {gain > 0 ? "+" : ""}{gain} хим.
          </span>
        )}
      </span>
    );
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
            <span className="whitespace-nowrap text-caption font-bold">{t.name}</span>
            {t.is_active && (
              <span className={`text-micro ${t.template_index === viewedIndex ? "text-bg-base/70" : "text-accent-lime"}`}>
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
          className="self-start text-caption font-semibold text-ink-mist-dim underline underline-offset-2"
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
              <p className="text-caption text-ink-mist">
                Навыки: действуют {activeSquadSkills.length} из {squadSkills.length}
              </p>
            )}
            <div className="mt-1 flex flex-wrap gap-1.5">
              <button
                onClick={() => autoFillMutation.mutate(false)}
                disabled={autoFillMutation.isPending}
                className="rounded-full bg-accent-lime/15 px-2.5 py-1 text-caption font-semibold text-accent-lime disabled:opacity-50"
              >
                Собрать лучший
              </button>
              <button
                onClick={() => autoFillMutation.mutate(true)}
                disabled={autoFillMutation.isPending}
                className="rounded-full bg-white/5 px-2.5 py-1 text-caption font-semibold text-ink-mist disabled:opacity-50"
              >
                Из Card Arena
              </button>
            </div>
          </div>
          {squad?.is_complete && (
            <span className="flex items-center gap-1 font-mono text-xs font-bold text-accent-cyan">
              <IconCheck size={14} />
              Заполнен
            </span>
          )}
        </div>

        <div className="mb-3">
          <BenchUpgradeHints hints={benchUpgrades} onApply={applyBenchUpgrade} busy={setCardsMutation.isPending} />
        </div>
        <ChemistryFrozenNote chemistry={chemistry} />
        <ChemistrySummary chemistry={chemistry} />
        <ChemistryHints hints={chemistryHints} onApply={applyChemistryHint} busy={setCardsMutation.isPending} />

        {tactics && (
          <div className="mb-3">
            <TacticsPanel
              style={squad?.style ?? "possession"} formation={squad?.formation ?? "4-3-3"} rules={tactics.rules}
              next={tactics.next && squad?.is_active ? { ...tactics.next, detail: `тур ${tactics.next.round}` } : null}
              busy={!squad || setTacticsMutation.isPending} onChange={updateTactics}
              note="Тактика действует со следующего тура. Смена схемы убирает с поля тех, кому нет места."
              help={<>
                <p>1. <b className="text-ink-chalk">Состав.</b> Твои 11 карточек по схеме; химия, тренер, стадион (дома), навыки и таланты работают как раньше.</p>
                <p>2. <b className="text-ink-chalk">Тактика — как в Card Arena.</b> Стиль даёт % к рейтингу своих линий, схема — небольшой крен в атаку или защиту. Если твой стиль бьёт стиль соперника, все твои игроки получают +{tactics.rules.edge_pct}%.</p>
                <p>3. <b className="text-ink-chalk">Игра.</b> Движок разыгрывает владение и моменты по рейтингам с учётом тактики: полузащита борется за мяч, нападающие — с защитниками, удары — против вратаря.</p>
                <p>4. <b className="text-ink-chalk">Случай.</b> Слабый иногда побеждает, но на дистанции 30 туров решают сила и тактика.</p>
              </>}
            />
          </div>
        )}

        <div ref={pitchRef} style={PITCH_STYLE} className="relative flex flex-col gap-3 overflow-hidden rounded-[22px] p-3 ring-1 ring-white/10">
          <PitchBackground />
          <ChemistryLinksOverlay containerRef={pitchRef} chemistry={chemistry} />
          {pitchRows(squad?.formation, (squad?.slots ?? []).map((s) => s.slot_code)).map((row) => { const category = row.category; return (
            <div key={row.key} className="relative flex justify-evenly gap-2">
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
                        <img decoding="async"
                          src={staticUrl(squad.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                          alt="" className="h-full w-full object-cover" loading="lazy"
                        />
                      </div>
                      <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-micro font-bold leading-none text-accent-cyan">Тренер</span>
                    </>
                  ) : (
                    <>
                      <IconPlus size={16} className="text-ink-mist-dim" />
                      <span className="text-micro text-ink-mist-dim">Тренер</span>
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
                        <img decoding="async"
                          src={staticUrl(squad.stadium.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                          alt="" className="h-full w-full object-cover" loading="lazy"
                        />
                      </div>
                      <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-micro font-bold leading-none text-accent-cyan">
                        +{Math.round(squad.stadium.boost_pct * 100)}%
                      </span>
                    </>
                  ) : (
                    <>
                      <IconPlus size={16} className="text-ink-mist-dim" />
                      <span className="text-micro text-ink-mist-dim">Стадион</span>
                    </>
                  )}
                </button>
              )}
              {inRow(row, squad?.slots ?? [])
                .map((slot) => (
                  <button
                    key={slot.slot_code}
                    data-chem-slot={slot.slot_code}
                    onClick={() => setPickerSlot(slot)}
                    disabled={setCardsMutation.isPending}
                    className="flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 disabled:opacity-60"
                  >
                    {slot.player ? (
                      <PitchCardTile
                        player={{ ...slot.player, rating: slot.match_rating ?? slot.player.rating }}
                        stars={slot.stars ?? 0}
                        pathStage={slot.path_stage}
                        prestige={slot.prestige ?? 0}
                        ratingDown={(slot.fit_pct ?? 100) < 100}
                        skillCode={slot.skill_code}
                        skillLevel={slot.skill_level}
                        skillInactiveReason={skillInactive(slot.skill_code, slot.player.position)}
                      >
                        <SlotPosition slot={slot} />
                        {chemistryOn && chemBySlot.has(slot.slot_code) && (
                          <ChemistryDiamonds
                            points={chemBySlot.get(slot.slot_code)!.points}
                            max={chemistry!.rules?.player_max ?? 3}
                            onPosition={chemBySlot.get(slot.slot_code)!.on_position}
                          />
                        )}
                      </PitchCardTile>
                    ) : (
                      <>
                        <IconPlus size={18} className="text-ink-mist-dim" />
                        <span className="font-mono text-micro font-bold text-accent-cyan">{slot.ideal_position}</span>
                      </>
                    )}
                  </button>
                ))}
            </div>
          ); })}
        </div>

        <p className="mt-2 text-center text-micro text-ink-mist-dim">
          Под картой — позиция места. На чужой позиции игрок слабее: в своей линии 90%, в чужой 75% — рейтинг станет красным.
        </p>

        {squad?.coach && (
          <div className="mt-3 rounded-xl bg-white/5 px-3 py-2">
            <p className="text-xs font-semibold text-ink-chalk">{squad.coach.display_name}</p>
            <p className="mt-0.5 text-caption text-ink-mist">
              {squad.coach.boosts.map((b) => `${BOOST_TYPE_LABELS[b.boost_type]} +${b.magnitude}`).join(" · ")}
            </p>
          </div>
        )}
        {squad?.stadium && (
          <div className="mt-3 rounded-xl bg-white/5 px-3 py-2">
            <p className="text-xs font-semibold text-ink-chalk">{squad.stadium.display_name}</p>
            <p className="mt-0.5 text-caption text-ink-mist">+{Math.round(squad.stadium.boost_pct * 100)}% к силе</p>
          </div>
        )}
      </section>

      {pickerSlot && (
        <CardPickerModal
          showSkills
          open
          title={`Место ${pickerSlot.ideal_position} · ${CATEGORY_LABELS[pickerSlot.category as FormationSlot["category"]]}`}
          cards={cardsForSlot(pickerSlot)}
          disabledCardIds={cardsForSlot(pickerSlot).filter((c) => usedPlayerIds.includes(c.player.id)).map((c) => c.id)}
          onSelect={(card) => assignSlot(pickerSlot, card)}
          onClose={() => { setPickerSlot(null); setPickerSearch(""); }}
          searchValue={pickerSearch}
          onSearchChange={setPickerSearch}
          cardNote={pickerChemistryNote}
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

// Mirrors lineup_service.slot_fit: own position (LB/LWB, RB/RWB count as
// one) 100 %, another position of the slot's line 90 %, anything else 75 %.
const EQUIVALENT: Record<string, string> = { LB: "LWB", LWB: "LB", RB: "RWB", RWB: "RB" };
function slotFitPct(position: string, slot: PersonalSquadSlot): number {
  if (position === slot.ideal_position || EQUIVALENT[position] === slot.ideal_position) return 100;
  return CATEGORY_POSITIONS[slot.category as FormationSlot["category"]]?.includes(position as never) ? 90 : 75;
}

/** Under a filled slot: the slot's own position, and what playing off it costs. */
function SlotPosition({ slot }: { slot: PersonalSquadSlot }) {
  const fit = slot.fit_pct ?? 100;
  const cut = slot.rating != null && slot.match_rating != null ? slot.rating + (slot.chemistry_bonus ?? 0) - slot.match_rating : 0;
  return (
    <span className={`mt-0.5 block text-center font-mono text-micro font-bold leading-tight ${fit < 100 ? "text-red-400" : "text-ink-mist"}`}>
      {slot.ideal_position}
      {fit < 100 && <span className="block font-normal">−{cut} ({fit}%)</span>}
    </span>
  );
}
