import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import CardPickerModal from "@/components/cards/CardPickerModal";
import PitchCardTile from "@/components/cards/PitchCardTile";
import MatchSkillNotes from "@/components/cards/MatchSkillNotes";
import MatchPathSummary from "@/components/path/MatchPathSummary";
import MatchSkillSummary from "@/components/cards/MatchSkillSummary";
import GameHero from "@/components/common/GameHero";
import { skillByCode, skillInactiveReason, useSkillCatalog } from "@/lib/cardSkills";
import UserCoachCardPickerModal from "@/components/cards/UserCoachCardPickerModal";
import UserStadiumCardPickerModal from "@/components/cards/UserStadiumCardPickerModal";
import EmptyState from "@/components/common/EmptyState";
import ShareButton from "@/components/common/ShareButton";
import MatchPitchView from "@/components/match/MatchPitchView";
import MatchSheet from "@/components/match/MatchSheet";
import MatchStatsTable from "@/components/match/MatchStatsTable";
import { ArenaDivisionCard, ArenaMatchReport, ArenaMatchupLine, ArenaOpponentCard } from "@/components/arena/ArenaPanels";
import { useTelegramMainButton } from "@/lib/useTelegramMainButton";
import BenchUpgradeHints from "@/components/squad/BenchUpgradeHints";
import { ChemistryDiamonds, ChemistryHints, ChemistryLinksOverlay, ChemistrySummary } from "@/components/squad/Chemistry";
import { chemistryGain, chemistrySwapHints, equipmentChemistryOf, type ChemistrySwapHint } from "@/lib/chemistry";
import {
  IconBall,
  IconBoot,
  IconCoin,
  IconGloves,
  IconGoal,
  IconPlus,
  IconSwap,
  IconUsers,
  IconWarning,
  type IconProps,
} from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchCollection } from "@/api/collection";
import {
  activateLineupTemplate,
  autoFillLineupTemplate,
  fetchLineupBenchUpgrades, fetchLineupTemplates, fetchUserCoachCards, fetchUserStadiumCards,
  renameLineupTemplate, setLineupTemplate, setLineupTemplateCoach, setLineupTemplateFormation, setLineupTemplateStadium,
  setLineupTemplateTactic,
  type BenchUpgrade,
} from "@/api/lineups";
import { actMatch, fetchArenaOpponent, fetchArenaStats, fetchMatchHistory, forfeitMatch, playMatch } from "@/api/matches";
import { staticUrl } from "@/lib/api";
import { BOOST_TYPE_LABELS } from "@/lib/coaches";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, TACTIC_LABELS, TACTICS, type FormationSlot } from "@/lib/formation";
import { formatGameError } from "@/lib/errors";
import { FORMATION_LABELS, formationLabel, inRow, pitchRows } from "@/lib/formationLayout";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import { useMatchGuardStore } from "@/store/matchGuardStore";
import type { LineupTactic, Match, MatchActionKind, MatchPendingMoment, MatchResult, UserCard } from "@/types";

const EVENT_STEP_MS = 950;

const ACTION_LABELS: Record<MatchActionKind, { label: string; Icon: (props: IconProps) => JSX.Element }> = {
  shoot: { label: "Ударить", Icon: IconBoot },
  pass: { label: "Отдать пас", Icon: IconSwap },
  tackle: { label: "Сделать подкат", Icon: IconUsers },
  block: { label: "Заблокировать удар", Icon: IconGoal },
  keeper: { label: "Довериться вратарю", Icon: IconGloves },
  strike: { label: "Ударить!", Icon: IconBoot },
};

export default function ArenaPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const { data: templates, isLoading: lineupLoading } = useQuery({ queryKey: ["lineup-templates"], queryFn: fetchLineupTemplates });
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const activeIndex = templates?.find((t) => t.is_active)?.template_index ?? 1;
  const viewedIndex = selectedIndex ?? activeIndex;
  const lineup = templates?.find((t) => t.template_index === viewedIndex);
  const { data: skillCatalog } = useSkillCatalog();
  const skillInactive = (code?: string | null, position?: string) =>
    skillInactiveReason(skillByCode(skillCatalog?.skills, code), "arena", position, skillCatalog?.rules.enabled ?? true);
  const lineupSkills = (lineup?.slots ?? []).filter((s) => s.card?.skill_code);
  const activeLineupSkills = lineupSkills.filter((s) => !skillInactive(s.card?.skill_code, s.card?.player.position));
  const [pickerSearch, setPickerSearch] = useState("");
  const { data: collectionPage } = useQuery({
    queryKey: ["collection-for-lineup", pickerSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: pickerSearch || undefined }),
  });
  const { data: stats } = useQuery({ queryKey: ["arena-stats"], queryFn: fetchArenaStats });
  const { data: history } = useQuery({ queryKey: ["match-history"], queryFn: fetchMatchHistory });

  const [pickerSlot, setPickerSlot] = useState<FormationSlot | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [lineupError, setLineupError] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);
  // The match plays in a sheet over the lineup. `matchReopened` = the sheet
  // was reopened for a match that already finished, so it shows the final
  // state instead of replaying (and never re-credits the reward).
  const [matchSheetOpen, setMatchSheetOpen] = useState(false);
  const [matchReopened, setMatchReopened] = useState(false);
  const [strengthHintOpen, setStrengthHintOpen] = useState(false);
  const pitchRef = useRef<HTMLDivElement>(null);
  const [coachPickerOpen, setCoachPickerOpen] = useState(false);
  const { data: coachCards } = useQuery({ queryKey: ["lineup", "coach-cards"], queryFn: fetchUserCoachCards });
  const [stadiumPickerOpen, setStadiumPickerOpen] = useState(false);
  const { data: stadiumCards } = useQuery({ queryKey: ["lineup", "stadium-cards"], queryFn: fetchUserStadiumCards });

  const setLineupMutation = useMutation({
    mutationFn: (slots: { slot_code: string; user_card_id: number }[]) => setLineupTemplate(viewedIndex, slots),
    onSuccess: () => { setLineupError(null); queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось обновить состав")),
  });

  const setTacticMutation = useMutation({
    mutationFn: (tactic: LineupTactic) => setLineupTemplateTactic(viewedIndex, tactic),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }),
  });

  const setFormationMutation = useMutation({
    mutationFn: (formation: string) => setLineupTemplateFormation(viewedIndex, formation),
    onSuccess: () => { haptic("light"); setLineupError(null); queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось сменить схему")),
  });

  // The next opponent is found once on the server and kept until that match
  // is played; the key follows the active squad's style/strength so the
  // matchup and chances refresh as soon as the player changes them.
  const activeLineup = templates?.find((t) => t.is_active);
  const { data: preview, isFetching: previewFetching } = useQuery({
    queryKey: ["arena-opponent", activeLineup?.tactic, activeLineup?.team_strength],
    queryFn: fetchArenaOpponent,
    enabled: !!activeLineup?.is_complete && !simulating,
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  });
  const activeStyleMutation = useMutation({
    mutationFn: (tactic: LineupTactic) => setLineupTemplateTactic(activeIndex, tactic),
    onSuccess: () => { haptic("light"); queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); },
  });

  const setCoachMutation = useMutation({
    mutationFn: (userCoachCardId: number | null) => setLineupTemplateCoach(viewedIndex, userCoachCardId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); setCoachPickerOpen(false); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось назначить тренера")),
  });

  const setStadiumMutation = useMutation({
    mutationFn: (userStadiumCardId: number | null) => setLineupTemplateStadium(viewedIndex, userStadiumCardId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); setStadiumPickerOpen(false); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось назначить стадион")),
  });

  const autoFillMutation = useMutation({
    mutationFn: () => autoFillLineupTemplate(viewedIndex),
    onSuccess: () => { haptic("medium"); setLineupError(null); queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось собрать состав")),
  });

  const activateMutation = useMutation({
    mutationFn: () => activateLineupTemplate(viewedIndex),
    onSuccess: () => { haptic("medium"); queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось переключить шаблон")),
  });

  const [renamingTemplate, setRenamingTemplate] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const renameMutation = useMutation({
    mutationFn: (name: string) => renameLineupTemplate(viewedIndex, name),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); setRenamingTemplate(false); },
  });

  const playMutation = useMutation({
    mutationFn: () => playMatch("medium"),
    onSuccess: (data) => {
      setMatch(data);
      setMatchError(null);
      setSimulating(true);
      queryClient.removeQueries({ queryKey: ["arena-opponent"] });
      setMatchReopened(false);
      setMatchSheetOpen(true);
      // Balance, stats and history only update once the simulation finishes
      // playing out (MatchSimulation's onFinished) so the result isn't spoiled.
    },
    onError: (err) => setMatchError(formatGameError(err, "Не удалось начать матч")),
  });

  const actMutation = useMutation({
    mutationFn: (action: MatchActionKind) => actMatch(match!.id, action),
    onSuccess: (data) => setMatch(data),
  });

  const forfeitMutation = useMutation({
    mutationFn: () => forfeitMatch(match!.id),
    onSuccess: (data) => {
      setMatch(data);
      setSimulating(false);
      queryClient.invalidateQueries({ queryKey: ["arena-stats"] });
      queryClient.invalidateQueries({ queryKey: ["match-history"] });
      hapticNotify("error");
      useMatchGuardStore.getState().deactivate();
    },
  });

  // Guards in-app navigation while a match is live, same as Тактико —
  // leaving mid-match costs the same -1 rating as playing it out and
  // losing, so quitting to dodge a loss isn't a viable strategy. The
  // confirm dialog (rendered globally) calls this same forfeit endpoint if
  // the player chooses to leave anyway.
  useEffect(() => {
    if (simulating && match?.status === "in_progress") {
      useMatchGuardStore.getState().activate(
        "Матч ещё не завершён. Если выйдешь сейчас, он будет засчитан как поражение.",
        () => { forfeitMatch(match.id).catch(() => {}); },
        `/matches/${match.id}/forfeit`,
      );
    } else {
      useMatchGuardStore.getState().deactivate();
    }
    return () => useMatchGuardStore.getState().deactivate();
  }, [simulating, match?.status, match?.id]);

  const { data: benchUpgrades } = useQuery({
    queryKey: ["lineup-templates", "bench", viewedIndex],
    queryFn: () => fetchLineupBenchUpgrades(viewedIndex),
    enabled: !!lineup,
  });
  const applyBenchUpgrade = (hint: BenchUpgrade) => {
    const slots = (lineup?.slots ?? [])
      .filter((s) => s.card && s.slot_code !== hint.slot_code)
      .map((s) => ({ slot_code: s.slot_code, user_card_id: s.card!.id }));
    slots.push({ slot_code: hint.slot_code, user_card_id: hint.suggested_card_id });
    setLineupMutation.mutate(slots);
  };

  const nativePlayButton = useTelegramMainButton({
    text: "Играть матч",
    onClick: () => playMutation.mutate(),
    visible: !simulating && match?.status !== "in_progress" && !matchSheetOpen,
    enabled: !!lineup?.is_complete,
    loading: playMutation.isPending,
  });

  if (lineupLoading) return <ListSkeleton />;

  // A player already fielded in another slot is blocked even via a duplicate
  // card copy (same player, different card id) — one player can't start twice.
  const usedPlayerIds = (pickerSlot
    ? lineup?.slots.filter((s) => s.card && s.slot_code !== pickerSlot.code)
    : lineup?.slots.filter((s) => s.card)
  )?.map((s) => s.card!.player.id) ?? [];

  const maxDiamond = lineup?.max_diamond ?? 1;
  // «Академия» cards are diamonds with a squad limit of their own.
  const maxPath = lineup?.max_path ?? 1;
  const isPlainDiamond = (p: { rarity: string; path_talent_code?: string | null }) => p.rarity === "diamond" && !p.path_talent_code;
  const otherSlots = (pickerSlot
    ? lineup?.slots.filter((s) => s.card && s.slot_code !== pickerSlot.code)
    : lineup?.slots.filter((s) => s.card)
  ) ?? [];
  const diamondCount = otherSlots.filter((s) => isPlainDiamond(s.card!.player)).length;
  const pathCount = otherSlots.filter((s) => !!s.card!.player.path_talent_code).length;
  const limitBlocked = (c: UserCard) =>
    (isPlainDiamond(c.player) && diamondCount >= maxDiamond) || (!!c.player.path_talent_code && pathCount >= maxPath);

  const cardsForSlot = (slot: FormationSlot): UserCard[] => {
    const positions = CATEGORY_POSITIONS[slot.category];
    return (collectionPage?.items ?? []).filter((c) => positions.includes(c.player.position));
  };

  const assignSlot = async (slot: FormationSlot, card: UserCard) => {
    const currentSlots = (lineup?.slots ?? [])
      .filter((s) => s.card && s.slot_code !== slot.code)
      .map((s) => ({ slot_code: s.slot_code, user_card_id: s.card!.id }));
    currentSlots.push({ slot_code: slot.code, user_card_id: card.id });
    try {
      await setLineupMutation.mutateAsync(currentSlots);
      setPickerSlot(null);
    } catch {
      // Error is surfaced via setLineupMutation's onError; keep the picker
      // open so the player can choose a different card instead of it
      // silently reverting to the previous slot state.
    }
  };

  // Neighbour-link chemistry (only when the server has it switched on):
  // per-slot points for the diamonds, and instant "what if" numbers for the
  // picker and the swap hints computed by the same rules the server returned.
  const chemistry = lineup?.chemistry;
  const chemistryOn = !!chemistry?.enabled;
  const chemBySlot = new Map((chemistry?.players ?? []).map((p) => [p.slot_code, p]));
  const chemSlots = (lineup?.slots ?? []).map((s) => ({
    slot_code: s.slot_code, ideal_position: s.ideal_position, player: s.card?.player ?? null,
    equipment: s.card ? equipmentChemistryOf(s.card) : null,
  }));
  const diamondsOutside = (slotCode: string) =>
    (lineup?.slots ?? []).filter((s) => s.card && s.slot_code !== slotCode && isPlainDiamond(s.card.player)).length;
  const pathOutside = (slotCode: string) =>
    (lineup?.slots ?? []).filter((s) => s.card && s.slot_code !== slotCode && !!s.card.player.path_talent_code).length;
  const chemistryHints = chemistryOn
    ? chemistrySwapHints(chemistry, chemSlots, (slot) => {
        const positions = CATEGORY_POSITIONS[(lineup?.slots.find((s) => s.slot_code === slot.slot_code)?.category ?? "GK") as FormationSlot["category"]];
        return (collectionPage?.items ?? [])
          .filter((c) => positions.includes(c.player.position))
          .filter((c) => !isPlainDiamond(c.player) || diamondsOutside(slot.slot_code) < maxDiamond)
          .filter((c) => !c.player.path_talent_code || pathOutside(slot.slot_code) < maxPath)
          .map((c) => ({ cardId: c.id, playerId: c.player.id, name: c.player.display_name, club: c.player.club, country: c.player.country, position: c.player.position }));
      })
    : [];
  const applyChemistryHint = (hint: ChemistrySwapHint) => {
    const slots = (lineup?.slots ?? [])
      .filter((s) => s.card && s.slot_code !== hint.slotCode)
      .map((s) => ({ slot_code: s.slot_code, user_card_id: s.card!.id }));
    slots.push({ slot_code: hint.slotCode, user_card_id: hint.cardId });
    setLineupMutation.mutate(slots);
  };
  const pickerChemistryNote = (card: UserCard) => {
    if (!chemistryOn || !pickerSlot) return null;
    const gain = chemistryGain(chemistry, chemSlots, pickerSlot.code, { ...card.player, ...equipmentChemistryOf(card) });
    if (gain == null) return null;
    return (
      <span className={`font-mono text-micro font-bold ${gain > 0 ? "text-accent-green" : gain < 0 ? "text-red-400" : "text-ink-mist-dim"}`}>
        {gain > 0 ? "+" : ""}{gain} хим.
      </span>
    );
  };

  const lastFive = (history ?? []).slice(0, 5).reverse();

  return (
    <div className="flex flex-col gap-5">
      <GameHero game="arena" title="Card Arena" />

      {stats?.division && <ArenaDivisionCard division={stats.division} rank={stats.arena_rank} />}

      {stats && (
        <div className="grid grid-cols-3 gap-2 text-center">
          <MiniStat label="Рейтинг лиги" value={stats.arena_rating} />
          <MiniStat label="В · Н · П" value={`${stats.matches_won}·${stats.matches_drawn}·${stats.matches_lost}`} />
          <div className="rounded-xl bg-bg-surface py-2">
            <div className="flex items-center justify-center gap-1">
              {lastFive.length ? (
                lastFive.map((m) => <FormBadge key={m.id} result={m.result} />)
              ) : (
                <span className="font-mono text-xs text-ink-mist-dim">—</span>
              )}
            </div>
            <p className="mt-1 text-micro text-ink-mist-dim">Форма</p>
          </div>
        </div>
      )}

      {lineupError && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{lineupError}</p>}

      <section className="flex gap-1.5 overflow-x-auto pb-1">
        {(templates ?? []).map((t) => (
          <button
            key={t.template_index}
            onClick={() => { setSelectedIndex(t.template_index); setRenamingTemplate(false); }}
            className={`flex shrink-0 flex-col items-center gap-0.5 rounded-xl px-3 py-1.5 ${
              t.template_index === viewedIndex ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
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
            className="rounded-xl bg-floodlight px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
          >
            Сохранить
          </button>
        </div>
      ) : (
        <button
          onClick={() => { setRenameValue(lineup?.name ?? ""); setRenamingTemplate(true); }}
          className="self-start text-caption font-semibold text-ink-mist-dim underline underline-offset-2"
        >
          Переименовать «{lineup?.name}»
        </button>
      )}

      {viewedIndex !== activeIndex && (
        <button
          onClick={() => activateMutation.mutate()}
          disabled={activateMutation.isPending}
          className="rounded-xl bg-accent-lime/10 px-3 py-2 text-center text-xs font-semibold text-accent-lime disabled:opacity-40"
        >
          {activateMutation.isPending ? "Переключаем..." : `Сделать «${lineup?.name}» активным для матчей`}
        </button>
      )}

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="font-display text-base font-bold text-ink-chalk">Состав {formationLabel(lineup?.formation ?? "4-3-3")}</p>
            {lineupSkills.length > 0 && (
              <p className="text-caption text-ink-mist">
                Навыки: действуют {activeLineupSkills.length} из {lineupSkills.length}
                {activeLineupSkills.length < lineupSkills.length && " (зачёркнутые здесь не работают)"}
              </p>
            )}
            <button
              onClick={() => autoFillMutation.mutate()}
              disabled={autoFillMutation.isPending}
              className="mt-1 rounded-full bg-accent-lime/15 px-2.5 py-1 text-caption font-semibold text-accent-lime disabled:opacity-50"
            >
              {autoFillMutation.isPending ? "Собираем..." : "Собрать лучший состав"}
            </button>
          </div>
          {lineup?.is_complete && (
            <button
              onClick={() => setStrengthHintOpen((v) => !v)}
              className="flex items-center gap-1 font-mono text-sm font-bold text-accent-cyan"
            >
              Сила: {lineup.team_strength}
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-white/10 text-micro font-bold text-ink-mist-dim">?</span>
            </button>
          )}
        </div>
        {strengthHintOpen && (
          <div className="mb-3 rounded-xl bg-white/5 px-3 py-2 text-caption leading-relaxed text-ink-mist">
            <p className="mb-1 font-semibold text-ink-chalk">Что влияет на силу состава:</p>
            <p>· Позиция игрока: 100% рейтинга на своей позиции, 90% на смежной, 75% не по профилю</p>
            <p>· Схема: определяет позиции и соседей для химии; атакующие схемы (3-4-3, 4-4-2) чуть усиливают атаку и ослабляют защиту, оборонительные (5-3-2, 4-3-3 с опорником) — наоборот</p>
            {chemistryOn ? (
              <p>· Химия: связи с соседями по схеме — каждое очко химии игрока добавляет рейтинг в матче</p>
            ) : (
              <p>· Химия: бонус за игроков одного клуба и одной страны в составе</p>
            )}
            <p>· Редкость карточки: чем выше редкость, тем больше вклад рейтинга в силу</p>
            <p>· Тренер: даёт бонус к силе по своей редкости</p>
            <p>· Стиль игры: каждый усиливает свою линию (Атака — нападение, Владение — полузащиту, Оборона — защиту и вратаря, Контратака — понемногу оба края), а против стиля соперника может дать ещё бонус</p>
            <p className="mt-1 text-ink-mist-dim">Поэтому простая замена на игрока с более высоким рейтингом не всегда увеличивает силу — важна ещё позиция, химия и тактика.</p>
          </div>
        )}
        <div className="mb-3">
          <BenchUpgradeHints hints={benchUpgrades} onApply={applyBenchUpgrade} busy={setLineupMutation.isPending} />
        </div>
        <ChemistrySummary chemistry={chemistry} />
        <ChemistryHints hints={chemistryHints} onApply={applyChemistryHint} busy={setLineupMutation.isPending} />
        <p className="mb-3 text-caption font-semibold">
          <span className={`rounded-full px-2.5 py-1 ${diamondCount >= maxDiamond ? "bg-rarity-diamond/20 text-rarity-diamond" : "bg-white/5 text-ink-mist"}`}>
            Диамантовых: {diamondCount}/{maxDiamond}
          </span>
          {pathCount > 0 && (
            <span className={`ml-1.5 rounded-full px-2.5 py-1 ${pathCount >= maxPath ? "bg-emerald-400/20 text-path" : "bg-white/5 text-ink-mist"}`}>
              🌱 Академия: {pathCount}/{maxPath}
            </span>
          )}
        </p>
        <div className="-mx-1 mb-3 flex gap-1.5 overflow-x-auto px-1 pb-1">
          {Object.keys(FORMATION_LABELS).map((code) => {
            const active = (lineup?.formation ?? "4-3-3") === code;
            return (
              <button
                key={code}
                onClick={() => !active && setFormationMutation.mutate(code)}
                disabled={setFormationMutation.isPending}
                className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-[11px] font-bold disabled:opacity-60 ${
                  active ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
                }`}
              >
                {FORMATION_LABELS[code]}
              </button>
            );
          })}
        </div>
        <div ref={pitchRef} className="relative flex flex-col gap-3 overflow-hidden rounded-2xl bg-gradient-to-b from-emerald-950/60 to-emerald-900/30 p-3">
          <ChemistryLinksOverlay containerRef={pitchRef} chemistry={chemistry} />
          <div className="pointer-events-none absolute inset-x-3 top-1/2 h-px -translate-y-1/2 bg-white/10" />
          <div className="pointer-events-none absolute left-1/2 top-1/2 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/10" />
          {pitchRows(lineup?.formation, (lineup?.slots ?? []).map((s) => s.slot_code)).map((row) => (
            <div key={row.key} className="relative flex justify-evenly gap-2">
              {inRow(row, lineup?.slots ?? [])
                .map((slot) => {
                  const formationSlot = { code: slot.slot_code, category: slot.category as FormationSlot["category"], idealPosition: slot.ideal_position };
                  return (
                    <button
                      key={slot.slot_code}
                      data-chem-slot={slot.slot_code}
                      onClick={() => setPickerSlot(formationSlot)}
                      disabled={setLineupMutation.isPending}
                      className="flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 disabled:opacity-60"
                    >
                      {slot.card ? (
                        <PitchCardTile
                          player={slot.card.player}
                          stars={slot.card.stars}
                          pathStage={slot.card.path_stage}
                          prestige={slot.card.prestige}
                          talentOverride={slot.card.talent_override}
                          skillCode={slot.card.skill_code}
                          skillLevel={slot.card.skill_level}
                          skillInactiveReason={skillInactive(slot.card.skill_code, slot.card.player.position)}
                        >
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
                          <span className="text-micro text-ink-mist-dim">{CATEGORY_LABELS[slot.category as FormationSlot["category"]]}</span>
                        </>
                      )}
                    </button>
                  );
                })}
              {row.category === "GK" && (
                <button
                  onClick={() => setCoachPickerOpen(true)}
                  disabled={setCoachMutation.isPending}
                  className={`absolute left-0 top-0 flex min-w-0 max-w-[72px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 ${setCoachMutation.isPending ? "opacity-60" : ""}`}
                >
                  {lineup?.coach ? (
                    <>
                      <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                        <img decoding="async"
                          src={staticUrl(lineup.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
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
              {row.category === "GK" && (
                <button
                  onClick={() => setStadiumPickerOpen(true)}
                  disabled={setStadiumMutation.isPending}
                  className={`absolute right-0 top-0 flex min-w-0 max-w-[72px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 ${setStadiumMutation.isPending ? "opacity-60" : ""}`}
                >
                  {lineup?.stadium ? (
                    <>
                      <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                        <img decoding="async"
                          src={staticUrl(lineup.stadium.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                          alt="" className="h-full w-full object-cover" loading="lazy"
                        />
                      </div>
                      <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-micro font-bold leading-none text-accent-cyan">
                        +{Math.round(lineup.stadium.boost_pct * 100)}%
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
            </div>
          ))}
        </div>
        {lineup?.coach && (
          <div className="mt-3 rounded-xl bg-white/5 px-3 py-2">
            <p className="text-xs font-semibold text-ink-chalk">{lineup.coach.display_name}</p>
            <p className="mt-0.5 text-caption text-ink-mist">
              {lineup.coach.boosts.map((b) => `${BOOST_TYPE_LABELS[b.boost_type]} +${b.magnitude}`).join(" · ")}
            </p>
          </div>
        )}
        {lineup?.stadium && (
          <div className="mt-3 rounded-xl bg-white/5 px-3 py-2">
            <p className="text-xs font-semibold text-ink-chalk">{lineup.stadium.display_name}</p>
            <p className="mt-0.5 text-caption text-ink-mist">+{Math.round(lineup.stadium.boost_pct * 100)}% к силе</p>
          </div>
        )}
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <p className="font-display text-sm font-bold text-ink-chalk">Стиль игры</p>
        <p className="mb-3 mt-0.5 text-caption leading-snug text-ink-mist">
          Атака бьёт Оборону, Оборона — Владение, Владение — Контратаку, Контратака — Атаку. Стиль соперника виден перед матчем.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {TACTICS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTacticMutation.mutate(t.value)}
              disabled={setTacticMutation.isPending}
              className={`rounded-xl px-1 py-2 text-center disabled:opacity-60 ${
                lineup?.tactic === t.value ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
              }`}
            >
              <p className="whitespace-nowrap text-xs font-bold leading-tight">{t.label}</p>
              <p className={`mt-0.5 text-micro leading-tight ${lineup?.tactic === t.value ? "text-bg-base/70" : "text-ink-mist-dim"}`}>
                {t.description} · бьёт «{TACTIC_LABELS[t.beats]}»
              </p>
            </button>
          ))}
        </div>
      </section>

      {preview && activeLineup?.is_complete && !simulating && (
        <div className={previewFetching ? "opacity-70 transition-opacity" : "transition-opacity"}>
          {viewedIndex !== activeIndex && (
            <p className="mb-1.5 text-caption text-ink-mist-dim">Играет активный состав «{activeLineup.name}»</p>
          )}
          <ArenaOpponentCard
            preview={preview}
            onStyle={(style) => activeStyleMutation.mutate(style)}
            stylePending={activeStyleMutation.isPending}
          />
        </div>
      )}

      {matchError && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{matchError}</p>}

      <section className={`flex flex-col gap-3 ${nativePlayButton ? "hidden" : ""}`}>
        <button
          onClick={() => playMutation.mutate()}
          disabled={!lineup?.is_complete || playMutation.isPending || simulating}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {playMutation.isPending || simulating ? "Идёт матч..." : "Играть матч"}
        </button>
      </section>

      {/* After the sheet is closed, the last result stays one tap away. */}
      {match && !matchSheetOpen && match.status === "finished" && (
        <button
          onClick={() => { setMatchReopened(true); setMatchSheetOpen(true); }}
          className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2.5 text-sm active:scale-[0.98]"
        >
          <span className="text-ink-mist">Последний матч · vs {match.opponent_name}</span>
          <span className="font-semibold text-accent-green">Открыть</span>
        </button>
      )}

      <MatchSheet
        open={!!match && matchSheetOpen}
        title="Матч Card Arena"
        footer={
          match && simulating && match.status === "in_progress" ? (
            <button
              onClick={() => forfeitMutation.mutate()}
              disabled={forfeitMutation.isPending}
              className="w-full text-center text-caption font-semibold text-ink-mist-dim underline underline-offset-2 active:scale-95"
            >
              Сдаться (засчитается поражение)
            </button>
          ) : match && !simulating ? (
            <div className="flex flex-col gap-2">
              {match.result === "win" && <ShareButton kind="match" id={match.id} label="Поделиться победой" />}
              {matchError && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{matchError}</p>}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setMatchSheetOpen(false)}
                  className="rounded-2xl bg-white/10 py-3 font-display text-sm font-bold text-ink-chalk active:scale-95"
                >
                  К составу
                </button>
                <button
                  onClick={() => playMutation.mutate()}
                  disabled={!lineup?.is_complete || playMutation.isPending}
                  className="rounded-2xl bg-floodlight py-3 font-display text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
                >
                  {playMutation.isPending ? "Начинаем..." : "Ещё матч"}
                </button>
              </div>
            </div>
          ) : null
        }
      >
        {match && (
          <MatchSimulation
            key={match.id}
            match={match}
            startRevealed={matchReopened}
            actPending={actMutation.isPending}
            onAct={(action) => actMutation.mutate(action)}
            onFinished={() => {
              setSimulating(false);
              if (match.reward_coins > 0) {
                updateBalance((useAuthStore.getState().user?.balance ?? 0) + match.reward_coins);
              }
              queryClient.invalidateQueries({ queryKey: ["arena-stats"] });
              queryClient.invalidateQueries({ queryKey: ["match-history"] });
              queryClient.invalidateQueries({ queryKey: ["arena-opponent"] });
              if (match.ladder?.rewards.length) {
                const coins = match.ladder.rewards.reduce((sum, r) => sum + r.coins, 0);
                updateBalance((useAuthStore.getState().user?.balance ?? 0) + coins);
              }
              hapticNotify(match.result === "win" ? "success" : match.result === "loss" ? "error" : "warning");
            }}
          />
        )}
      </MatchSheet>

      <section>
        <p className="mb-2 font-display text-base font-bold text-ink-chalk">История матчей</p>
        {!history?.length ? (
          <EmptyState icon={IconBall} title="Матчей ещё не было" />
        ) : (
          <div className="flex flex-col gap-2">
            {history.slice(0, 5).map((m) => (
              <div key={m.id} className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-sm">
                <span className="min-w-0 truncate text-ink-mist">vs {m.opponent_name}</span>
                <span className="flex shrink-0 items-center gap-2">
                  {m.ladder && (
                    <span className={`font-mono text-caption ${m.ladder.delta > 0 ? "text-accent-green" : m.ladder.delta < 0 ? "text-red-400" : "text-ink-mist-dim"}`}>
                      {m.ladder.delta > 0 ? "+" : ""}{m.ladder.delta}
                    </span>
                  )}
                  <span className={`font-mono font-bold ${m.result === "win" ? "text-accent-green" : m.result === "loss" ? "text-red-400" : "text-ink-mist"}`}>
                    {m.user_score}:{m.opponent_score}
                  </span>
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {pickerSlot && (
        <CardPickerModal
          showSkills
          open
          title={`Выбери на позицию ${CATEGORY_LABELS[pickerSlot.category]}`}
          cards={cardsForSlot(pickerSlot)}
          disabledCardIds={cardsForSlot(pickerSlot)
            .filter((c) => usedPlayerIds.includes(c.player.id) || limitBlocked(c))
            .map((c) => c.id)}
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

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-bg-surface py-2">
      <p className="font-mono text-sm font-bold text-ink-chalk">{value}</p>
      <p className="text-micro text-ink-mist-dim">{label}</p>
    </div>
  );
}

function FormBadge({ result }: { result: MatchResult | null }) {
  const letter = result === "win" ? "W" : result === "loss" ? "L" : "D";
  const className =
    result === "win"
      ? "bg-accent-green/20 text-accent-green"
      : result === "loss"
        ? "bg-red-500/20 text-red-400"
        : "bg-white/10 text-ink-mist";
  return (
    <span className={`flex h-5 w-5 items-center justify-center rounded-full font-mono text-micro font-bold ${className}`}>
      {letter}
    </span>
  );
}

function MatchSimulation({
  match,
  actPending,
  onAct,
  onFinished,
  startRevealed = false,
}: {
  match: Match;
  actPending: boolean;
  onAct: (action: MatchActionKind) => void;
  onFinished: () => void;
  /** Reopening an already-finished match: show it as played, don't replay it. */
  startRevealed?: boolean;
}) {
  const [revealedCount, setRevealedCount] = useState(startRevealed ? match.events.length : 0);
  const [autoSkip, setAutoSkip] = useState(false);
  const [flashKey, setFlashKey] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  // A reopened, already-played match must not re-credit the reward or
  // re-flash its goals.
  const finishedFiredRef = useRef(startRevealed);
  const prevRevealedRef = useRef(startRevealed ? match.events.length : 0);
  const ackedBreakawayRef = useRef(-1);

  const total = match.events.length;
  const caughtUp = revealedCount >= total;
  const isFinished = match.status === "finished";

  // A breakaway goal (opponent, empty net) has no meaningful save choice —
  // it still gets a beat of its own instead of just appearing in the log,
  // so it doesn't read as a sudden, unexplained goal.
  const nextEvent = !caughtUp ? match.events[revealedCount] : null;
  const isBreakawayNext =
    !!nextEvent &&
    nextEvent.team === "opponent" &&
    nextEvent.payload?.shot_type === "empty_net" &&
    ackedBreakawayRef.current !== revealedCount;

  useEffect(() => {
    if (caughtUp) {
      if (isFinished && !finishedFiredRef.current) {
        finishedFiredRef.current = true;
        onFinished();
      }
      return;
    }
    if (autoSkip) {
      setRevealedCount(total);
      return;
    }
    if (isBreakawayNext) return; // wait for the player to acknowledge it
    timerRef.current = setTimeout(() => {
      if (["goal", "save", "blocked"].includes(match.events[revealedCount]?.event_type)) haptic("medium");
      setRevealedCount((c) => c + 1);
    }, EVENT_STEP_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealedCount, caughtUp, isFinished, autoSkip, isBreakawayNext, total]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [revealedCount, caughtUp, isFinished]);

  // Auto-play any pending action while skipping, so the match resolves
  // itself all the way to the final result without further input.
  useEffect(() => {
    if (!autoSkip || !caughtUp || isFinished || actPending) return;
    const pending = match.pending_moment;
    if (!pending) return;
    const action = pending.actions[Math.floor(Math.random() * pending.actions.length)];
    onAct(action);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSkip, caughtUp, isFinished, actPending, match]);

  useEffect(() => {
    if (revealedCount > prevRevealedRef.current) {
      const newly = match.events.slice(prevRevealedRef.current, revealedCount);
      if (newly.some((e) => e.event_type === "goal" && e.team === "user")) setFlashKey((k) => k + 1);
    }
    prevRevealedRef.current = revealedCount;
  }, [revealedCount, match.events]);

  const skip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setAutoSkip(true);
  };

  const ackBreakaway = () => {
    ackedBreakawayRef.current = revealedCount;
    setRevealedCount((c) => c + 1);
  };

  const revealed = match.events.slice(0, revealedCount);
  const currentMinute = revealed.length ? revealed[revealed.length - 1].minute : 0;
  const pendingMoment = caughtUp && !isFinished && !autoSkip ? match.pending_moment : null;
  const showFinal = caughtUp && isFinished;

  // Keep the pitch on the chance the player just answered until its outcome
  // is revealed, instead of snapping back while the action request is in
  // flight and the next event waits for its reveal tick.
  const [heldMoment, setHeldMoment] = useState<{ team: string; shot_type: string; at: number } | null>(null);
  useEffect(() => {
    if (pendingMoment) setHeldMoment({ team: pendingMoment.team, shot_type: pendingMoment.shot_type, at: revealedCount });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingMoment?.seq]);
  const pitchMoment = pendingMoment ?? (heldMoment && heldMoment.at === revealedCount ? heldMoment : null);

  // The live score only counts goals among the *revealed* events, so it
  // climbs to the final score in step with the commentary instead of
  // spoiling the outcome the instant the match starts.
  const liveUserScore = revealed.filter((e) => e.event_type === "goal" && e.team === "user").length;
  const liveOpponentScore = revealed.filter((e) => e.event_type === "goal" && e.team === "opponent").length;

  return (
    <section className="relative flex min-h-0 flex-1 flex-col">
      {flashKey > 0 && (
        <div
          key={flashKey}
          className="pointer-events-none absolute inset-0 z-10 rounded-2xl border-2 border-accent-green animate-goal-flash"
        />
      )}

      <div className="flex shrink-0 items-center justify-between">
        <span className="font-mono text-xs text-ink-mist-dim">
          {showFinal ? "Матч завершён" : autoSkip ? "Пропускаем матч..." : `${currentMinute}' · идёт матч...`}
        </span>
        {/* Visible any time there's still something to skip through — including
            while waiting on the player's own action choice (caughtUp && !isFinished),
            not just during the event-by-event reveal — only hidden once the match
            has actually finished or a skip is already in progress. */}
        {!autoSkip && !showFinal && (
          <button onClick={skip} className="rounded-full bg-white/10 px-3 py-1 text-caption font-semibold text-ink-chalk">
            Пропустить
          </button>
        )}
      </div>

      {/* You first, as before — and the pitch/stats below keep you on the
          left too, so the numbers always line up with the sides. */}
      <p className="mt-1 shrink-0 text-center font-mono text-3xl font-bold tabular-nums text-ink-chalk">
        {liveUserScore} : {liveOpponentScore}
      </p>
      <ArenaMatchupLine match={match} />

      {/* The win/draw/loss verdict and reward stay hidden until the
          simulation actually finishes playing out, even though the live
          score above already tracks along with it. */}
      {showFinal && (
        <p
          className={`mt-1 flex shrink-0 items-center justify-center gap-1 text-center font-display text-sm font-bold ${
            match.result === "win" ? "text-accent-green" : match.result === "loss" ? "text-red-400" : "text-ink-mist"
          }`}
        >
          {match.result === "win" ? "Победа!" : match.result === "loss" ? "Поражение" : "Ничья"} · +{match.reward_coins}
          <IconCoin size={13} />
        </p>
      )}

      {/* Live: the schematic pitch. After the whistle the pitch has nothing
          left to say, so the summary takes its place, in view without scrolling. */}
      {/* After the whistle the report + stats + log are taller than the
          sheet: they scroll together, so the footer buttons stay reachable.
          Live, only the commentary log scrolls under the pitch. */}
      <div className={showFinal ? "mt-3 min-h-0 flex-1 overflow-y-auto overscroll-contain pb-2" : "contents"}>
      <div className={showFinal ? "shrink-0" : "mt-3 shrink-0"}>
        {showFinal ? (
          <div className="flex flex-col gap-2">
            <ArenaMatchReport match={match} />
            <MatchStatsTable events={match.events} opponentName={match.opponent_name} />
            <MatchSkillSummary events={match.events} />
            <MatchPathSummary match={match} />
          </div>
        ) : (
          <MatchPitchView events={revealed} opponentName={match.opponent_name} pending={pitchMoment} />
        )}
      </div>

      <div
        ref={logRef}
        className={showFinal ? "mt-3 space-y-1 text-xs" : "mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto pb-2 text-xs"}
      >
        {revealed.map((e, i) => (
          <p
            key={i}
            className={`${e.team === "user" ? "text-accent-green" : "text-ink-mist"} ${
              Array.isArray(e.payload?.talents) && e.payload.talents.length ? "-mx-1 rounded-md bg-path/10 px-1" : ""
            }`}
          >
            <span className="font-mono text-ink-mist-dim">{e.minute}&apos;</span> {e.description}
            <MatchSkillNotes event={e} />
          </p>
        ))}
      </div>
      </div>

      {isBreakawayNext && !autoSkip && (
        <div className="mt-3 flex shrink-0 flex-col items-center gap-3 rounded-2xl bg-black/20 p-4 text-center">
          <p className="text-sm font-semibold text-ink-chalk">
            <span className="inline-flex items-center gap-1.5"><IconWarning size={15} className="shrink-0 text-amber-300" />Соперник выходит один на один с твоим вратарём!</span>
          </p>
          <button
            onClick={ackBreakaway}
            className="rounded-2xl bg-white/10 px-8 py-3 font-display text-base font-bold text-ink-chalk active:scale-95"
          >
            Смотреть
          </button>
        </div>
      )}

      {pendingMoment && <ActionPrompt pending={pendingMoment} disabled={actPending} onAct={onAct} />}
    </section>
  );
}

function ActionPrompt({
  pending,
  disabled,
  onAct,
}: {
  pending: MatchPendingMoment;
  disabled: boolean;
  onAct: (action: MatchActionKind) => void;
}) {
  // Subtitle under a button shows the actor it concerns, if any — the
  // shooter for "shoot", the teammate for "pass". Defense actions all
  // concern the same named defender, already mentioned in the situation
  // text above, so no per-button subtitle is needed there.
  const subtitleFor = (action: MatchActionKind): string | null => {
    if (action === "shoot") return pending.actors.shooter?.name ?? null;
    if (action === "pass") return pending.actors.pass_target?.name ?? null;
    return null;
  };

  return (
    <div className="mt-3 flex shrink-0 flex-col items-center gap-3 rounded-2xl bg-black/20 p-4 text-center">
      <p className="text-sm font-semibold text-ink-chalk">{pending.description}</p>
      <div className={`grid gap-2 ${pending.actions.length === 1 ? "grid-cols-1" : pending.actions.length === 2 ? "grid-cols-2" : "grid-cols-3"}`}>
        {pending.actions.map((action) => {
          const { label, Icon } = ACTION_LABELS[action];
          const subtitle = subtitleFor(action);
          return (
            <button
              key={action}
              onClick={() => onAct(action)}
              disabled={disabled}
              className="flex flex-col items-center gap-1.5 rounded-2xl bg-bg-surface px-4 py-3 text-sm font-semibold text-ink-chalk active:scale-90 disabled:opacity-40"
            >
              <Icon size={16} />
              {label}
              {subtitle && <span className="text-micro font-normal text-ink-mist-dim">{subtitle}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
