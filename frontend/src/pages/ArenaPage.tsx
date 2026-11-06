import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import CardPickerModal from "@/components/cards/CardPickerModal";
import StickyActionBar from "@/components/common/StickyActionBar";
import CardSkillBadge from "@/components/cards/CardSkillBadge";
import { PitchTile } from "@/components/career/PlayerTile";
import MatchSkillNotes from "@/components/cards/MatchSkillNotes";
import MatchPathSummary from "@/components/path/MatchPathSummary";
import MatchSkillSummary from "@/components/cards/MatchSkillSummary";
import { skillByCode, skillInactiveReason, useSkillCatalog } from "@/lib/cardSkills";
import UserCoachCardPickerModal from "@/components/cards/UserCoachCardPickerModal";
import UserStadiumCardPickerModal from "@/components/cards/UserStadiumCardPickerModal";
import EmptyState from "@/components/common/EmptyState";
import ShareButton from "@/components/common/ShareButton";
import MatchPitchView from "@/components/match/MatchPitchView";
import MatchSheet from "@/components/match/MatchSheet";
import MatchStatsTable from "@/components/match/MatchStatsTable";
import { ArenaCupPanel, ArenaDefenseList } from "@/components/arena/ArenaExtras";
import {
  ArenaGoalOverlay, ArenaHalftimePrompt, ArenaLateCallPrompt, ArenaMomentPrompt, ArenaPenaltyScene, type ArenaAct,
} from "@/components/arena/ArenaLive";
import {
  ArenaDivisionCard, ArenaKeyDuel, ArenaLimitPanel, ArenaLinesRow, ArenaMatchReport, ArenaMatchupLine, ArenaSquadShell, ArenaOpponentCard, ArenaSheet, ArenaStatusStrip, ArenaTile,
  ArenaTileSide, OpponentMalusNote,
} from "@/components/arena/ArenaPanels";
import BenchUpgradeHints from "@/components/squad/BenchUpgradeHints";
import { ChemistryFlask, ChemistryHints, ChemistryLinksOverlay, ChemistrySummary } from "@/components/squad/Chemistry";
import PitchBackground from "@/components/squad/PitchBackground";
import { chemistryGain, chemistrySwapHints, equipmentChemistryOf, type ChemistrySwapHint } from "@/lib/chemistry";
import { IconBall, IconCoin, IconHistory, IconShirt, IconSwords, IconTrophy, IconWarning } from "@/components/icons";
import { ListSkeleton, Skeleton } from "@/components/common/Skeleton";
import { fetchCollection } from "@/api/collection";
import {
  activateLineupTemplate,
  autoFillLineupTemplate,
  fetchLineupBenchUpgrades, fetchLineupTemplates, fetchUserCoachCards, fetchUserStadiumCards,
  renameLineupTemplate, setLineupTemplate, setLineupTemplateCoach, setLineupTemplateFormation, setLineupTemplateStadium,
  setLineupTemplateTactic,
  type BenchUpgrade,
} from "@/api/lineups";
import {
  actMatch, fetchActiveMatch, fetchArenaOpponent, fetchArenaStats, fetchDefenseLog, fetchMatch, fetchRecentMatches,
  forfeitMatch, markDefenseSeen, playMatch, takeRevenge, type MatchActExtra,
} from "@/api/matches";
import { staticUrl } from "@/lib/api";
import { artOf } from "@/lib/gameArt";
import { boostText } from "@/lib/coaches";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, onIdealPosition, TACTIC_LABELS, TACTICS, type FormationSlot } from "@/lib/formation";
import { formatGameError } from "@/lib/errors";
import { FORMATION_LABELS, formationLabel, inRow, pitchRows } from "@/lib/formationLayout";
import { pathFrameClass } from "@/lib/pathCards";
import { playSound } from "@/lib/sound";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import { useMatchGuardStore } from "@/store/matchGuardStore";
import ArenaNewbieGuide from "@/components/newbie/ArenaNewbieGuide";
import type { ArenaActionKind, ArenaDivision, LineupTactic, Match, MatchEvent, UserCard } from "@/types";
import { personKey } from "@/lib/person";

/** The match breathes: a held breath before a shot's outcome, a quick filler. */
/** The hourly limit stays out of sight until it is about to matter. */
const LOW_MATCHES_LEFT = 3;
const QUICK_STEP_MS = 550;
const SHOT_STEP_MS = 1500;
const GOAL_HOLD_MS = 2100;
const BREAKAWAY_HOLD_MS = 2500;
const SHOT_OUTCOMES = new Set(["goal", "save", "shot", "blocked"]);

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
  const [pickerSlot, setPickerSlot] = useState<FormationSlot | null>(null);
  // The picker asks the server for its line, so a bench deeper than the top
  // hundred is still there.
  const { data: pickerPage } = useQuery({
    queryKey: ["collection-for-lineup", pickerSlot?.category, pickerSearch],
    queryFn: () => fetchCollection({
      page_size: 100, sort_by: "rating", sort_dir: "desc", search: pickerSearch || undefined, position_category: pickerSlot?.category,
    }),
    enabled: !!pickerSlot,
  });
  const { data: stats } = useQuery({
    queryKey: ["arena-stats"],
    queryFn: fetchArenaStats,
    refetchInterval: (query) => (query.state.data?.hourly_left === 0 ? 30_000 : false),
  });
  const { data: history } = useQuery({ queryKey: ["arena-recent"], queryFn: fetchRecentMatches });
  const { data: defenseItems } = useQuery({ queryKey: ["arena-defense"], queryFn: fetchDefenseLog });
  const { data: activeOnOpen } = useQuery({ queryKey: ["arena-active"], queryFn: fetchActiveMatch, staleTime: Infinity, gcTime: 0 });
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
  const [sheet, setSheet] = useState<"division" | "cup" | "defense" | "history" | "templates" | "formations" | "skills" | "tips" | null>(null);
  // The main screen is the next match: the squad folds away once it's ready
  // (a newcomer or an unfinished squad sees it open, the guide points at it).
  const [squadToggled, setSquadToggled] = useState<boolean | null>(null);
  const swipeFrom = useRef<{ x: number; y: number } | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const pitchRef = useRef<HTMLDivElement>(null);
  const tacticsRef = useRef<HTMLElement>(null);
  const playRef = useRef<HTMLButtonElement>(null);
  const [finishedMatch, setFinishedMatch] = useState<Match | null>(null);
  const [coachPickerOpen, setCoachPickerOpen] = useState(false);
  const matchesPlayed = stats ? stats.matches_won + stats.matches_drawn + stats.matches_lost : 0;
  const squadOpen = squadToggled ?? (!!stats && !!lineup && (matchesPlayed === 0 || !lineup.is_complete));
  const { data: coachCards } = useQuery({ queryKey: ["lineup", "coach-cards"], queryFn: fetchUserCoachCards, enabled: coachPickerOpen });
  const [stadiumPickerOpen, setStadiumPickerOpen] = useState(false);
  const { data: stadiumCards } = useQuery({ queryKey: ["lineup", "stadium-cards"], queryFn: fetchUserStadiumCards, enabled: stadiumPickerOpen });

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
    queryKey: ["arena-opponent", activeLineup?.template_index, activeLineup?.tactic, activeLineup?.formation, activeLineup?.team_strength],
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

  const goLive = (data: Match) => {
    setMatch(data);
    setMatchError(null);
    setSimulating(true);
    setMatchReopened(false);
    setMatchSheetOpen(true);
  };

  // A match cut short by a crash or a closed app comes back as it stands.
  useEffect(() => {
    if (activeOnOpen && !match) goLive(activeOnOpen);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeOnOpen]);

  const playMutation = useMutation({
    mutationFn: (mode: "ladder" | "cup" = "ladder") => playMatch("medium", mode),
    onSuccess: (data) => {
      goLive(data);
      queryClient.removeQueries({ queryKey: ["arena-opponent"] });
      // Balance, stats and history only update once the simulation finishes
      // playing out (MatchSimulation's onFinished) so the result isn't spoiled.
    },
    onError: (err) => setMatchError(formatGameError(err, "Не удалось начать матч")),
  });

  const actMutation = useMutation({
    mutationFn: ({ action, extra }: { action: ArenaActionKind; extra?: MatchActExtra }) => actMatch(match!.id, action, extra),
    onSuccess: (data) => setMatch(data),
    // A stale answer (a retry, two taps): show what the server has now.
    onError: () => { fetchMatch(match!.id).then(setMatch).catch(() => {}); },
  });
  const onAct: ArenaAct = (action, extra) => actMutation.mutate({ action, extra });

  const openPlayed = useMutation({
    mutationFn: fetchMatch,
    onSuccess: (data) => { setMatch(data); setMatchReopened(true); setMatchSheetOpen(true); },
  });

  const defenseSeen = useMutation({
    mutationFn: markDefenseSeen,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["arena-stats"] }),
  });
  const revengeMutation = useMutation({
    mutationFn: takeRevenge,
    onSuccess: (data) => {
      haptic("medium");
      queryClient.setQueriesData({ queryKey: ["arena-opponent"] }, data);
      queryClient.invalidateQueries({ queryKey: ["arena-defense"] });
      previewRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    },
    onError: (err) => setMatchError(formatGameError(err, "Реванш недоступен")),
  });

  const forfeitMutation = useMutation({
    mutationFn: () => forfeitMatch(match!.id),
    onSuccess: (data) => {
      setMatch(data);
      setSimulating(false);
      queryClient.invalidateQueries({ queryKey: ["arena-stats"] });
      queryClient.invalidateQueries({ queryKey: ["arena-recent"] });
      hapticNotify("error");
      useMatchGuardStore.getState().deactivate();
    },
  });

  // Guards in-app navigation while a match is live, same as Тактико: leaving
  // through the confirm dialog is a forfeit. A closed app or a crash is not
  // (no forfeit path for pagehide): the match waits, GET /matches/active
  // brings it back and an abandoned one closes as a loss on the server.
  useEffect(() => {
    if (simulating && match?.status === "in_progress") {
      useMatchGuardStore.getState().activate(
        "Матч ещё не завершён. Если выйдешь сейчас, он будет засчитан как поражение.",
        () => { forfeitMatch(match.id).catch(() => {}); },
      );
    } else {
      useMatchGuardStore.getState().deactivate();
    }
    return () => useMatchGuardStore.getState().deactivate();
  }, [simulating, match?.status, match?.id]);

  const { data: benchUpgrades } = useQuery({
    queryKey: ["lineup-templates", "bench", viewedIndex],
    queryFn: () => fetchLineupBenchUpgrades(viewedIndex),
    enabled: !!lineup && squadOpen,
  });
  // Swap hints look through the whole bench, so only an open squad asks for it.
  const { data: hintPool } = useQuery({
    queryKey: ["collection-for-lineup", "hints"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
    enabled: squadOpen && !!lineup?.chemistry?.enabled,
  });
  const applyBenchUpgrade = (hint: BenchUpgrade) => {
    const slots = (lineup?.slots ?? [])
      .filter((s) => s.card && s.slot_code !== hint.slot_code)
      .map((s) => ({ slot_code: s.slot_code, user_card_id: s.card!.id }));
    slots.push({ slot_code: hint.slot_code, user_card_id: hint.suggested_card_id });
    setLineupMutation.mutate(slots);
  };

  if (lineupLoading) return <ListSkeleton />;

  // A player already fielded in another slot is blocked even via a duplicate
  // card copy (same player, different card id) — one player can't start twice.
  // One footballer once: other copies / versions of a player already in the XI are blocked.
  const usedPersons = (pickerSlot
    ? lineup?.slots.filter((s) => s.card && s.slot_code !== pickerSlot.code)
    : lineup?.slots.filter((s) => s.card)
  )?.map((s) => personKey(s.card!.player)) ?? [];

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
    return (pickerPage?.items ?? []).filter((c) => positions.includes(c.player.position));
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
        return (hintPool?.items ?? [])
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
  const chosenTactic = TACTICS.find((t) => t.value === lineup?.tactic);
  const limitReached = stats?.hourly_left === 0;

  const cardShown = !!preview && !!activeLineup?.is_complete && !simulating;
  const tileRow = (
  <div className={`grid divide-x divide-white/10 border-t border-white/10 ${stats?.cup?.enabled ? "grid-cols-3" : "grid-cols-2"}`}>
    {stats?.cup?.enabled && (
      <ArenaTile
        icon={<IconTrophy size={17} className="text-amber-300" />}
        value={`${stats.cup.rounds_won}/${stats.cup.total_rounds}`}
        label="Кубок"
        tone={stats.cup.open && stats.cup.status !== "lost" && stats.cup.status !== "champion" ? "amber" : undefined}
        onClick={() => setSheet("cup")}
      />
    )}
    <ArenaTile
      icon={<IconSwords size={17} className="text-red-300" />}
      value={defenseItems?.length ?? 0}
      label="Атаки"
      badge={stats?.defense_unread}
      onClick={() => { setSheet("defense"); if (stats?.defense_unread) defenseSeen.mutate(); }}
    />
    <ArenaTile icon={<IconHistory size={17} className="text-accent-cyan" />} label="История" onClick={() => setSheet("history")} />
  </div>
  );

  // Newbies are walked through the style right on the page.
  const extrasInSheet = matchesPlayed > 0;
  const tipsCount = (benchUpgrades?.length ?? 0) + chemistryHints.length;
  const styleBlock = (
      <section ref={tacticsRef}>
        <div className="grid grid-cols-4 gap-1">
          {TACTICS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTacticMutation.mutate(t.value)}
              disabled={setTacticMutation.isPending}
              className={`rounded-xl py-2 text-center text-micro font-bold leading-tight disabled:opacity-60 ${
                lineup?.tactic === t.value ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {chosenTactic && (
          <p className="mt-1.5 text-center text-micro text-ink-mist-dim">
            {chosenTactic.description} · бьёт «{TACTIC_LABELS[chosenTactic.beats]}»
          </p>
        )}
      </section>
  );
  const tipsBlock = (
    <>
      <BenchUpgradeHints hints={benchUpgrades} onApply={applyBenchUpgrade} busy={setLineupMutation.isPending} />
      <ChemistrySummary chemistry={chemistry} />
      <ChemistryHints hints={chemistryHints} onApply={applyChemistryHint} busy={setLineupMutation.isPending} />
    </>
  );

  const tabBar = (
    <div role="tablist" className="grid grid-cols-2">
      {([[false, "Матч", IconBall], [true, "Состав", IconShirt]] as const).map(([value, label, Icon]) => (
        <button
          key={label}
          role="tab"
          aria-selected={squadOpen === value}
          onClick={() => setSquadToggled(value)}
          className={`flex items-center justify-center gap-1.5 py-2.5 text-sm font-bold transition ${squadOpen === value ? "text-accent-lime" : `bg-black/55 text-ink-mist ${value ? "rounded-bl-2xl" : "rounded-br-2xl"}`}`}
        >
          <Icon size={16} />
          {label}
        </button>
      ))}
    </div>
  );

  return (
    <div
      className="flex min-h-[calc(100dvh-10.6rem-env(safe-area-inset-bottom,0px))] flex-col gap-3"
      onTouchStart={(e) => { swipeFrom.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }; }}
      onTouchEnd={(e) => {
        const from = swipeFrom.current;
        swipeFrom.current = null;
        if (!from) return;
        const dx = e.changedTouches[0].clientX - from.x;
        const dy = e.changedTouches[0].clientY - from.y;
        if (Math.abs(dx) > 60 && Math.abs(dx) > 2 * Math.abs(dy)) setSquadToggled(dx < 0);
      }}
    >
      {stats?.division && (
        <ArenaStatusStrip division={stats.division} form={lastFive.map((m) => m.result)} onOpen={() => setSheet("division")} />
      )}
      {!squadOpen && !cardShown && tabBar}

      {!squadOpen && <>
        {matchError && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{matchError}</p>}

        {preview && activeLineup?.is_complete && !simulating ? (
          <div ref={previewRef} className={previewFetching ? "opacity-70 transition-opacity" : "transition-opacity"}>
            <ArenaOpponentCard
              preview={preview}
              onStyle={(style) => activeStyleMutation.mutate(style)}
              stylePending={activeStyleMutation.isPending}
              tabs={tabBar}
              bottomTabs={tileRow}
              lines={<ArenaLinesRow lines={preview.lines} />}
              background={artOf("arena-stadium")}
            />
          </div>
        ) : activeLineup?.is_complete ? (
          <Skeleton className="h-72 rounded-3xl" />
        ) : null}

        {cardShown && preview?.key_duel && <ArenaKeyDuel duel={preview.key_duel} />}

        {!cardShown && tileRow}
      </>}

      {squadOpen && <ArenaSquadShell tabs={tabBar} bottomTabs={<div className="[@media(max-height:760px)]:hidden">{tileRow}</div>}>
      <div className="flex items-center gap-1.5">
        <button onClick={() => setSheet("templates")} className="min-w-0 truncate rounded-full bg-white/5 px-3 py-1.5 text-caption font-bold text-ink-chalk">
          {lineup?.name} ▾
        </button>
        <button onClick={() => setSheet("formations")} className="min-w-0 truncate rounded-full bg-white/5 px-3 py-1.5 text-caption font-bold text-ink-chalk">
          {formationLabel(lineup?.formation ?? "4-3-3")} ▾
        </button>
        {extrasInSheet && (
          <button
            onClick={() => setSheet("tips")}
            className="ml-auto flex shrink-0 items-center gap-1 rounded-full bg-accent-lime/15 px-2.5 py-1.5 text-caption font-bold text-accent-lime"
          >
            Советы
            {tipsCount > 0 && <span className="rounded-full bg-accent-lime px-1 font-mono text-micro font-bold leading-4 text-bg-base">{tipsCount}</span>}
          </button>
        )}
        {lineup?.is_complete && (
          <button
            onClick={() => setStrengthHintOpen(true)}
            className={`-my-2 flex shrink-0 items-center gap-1 py-2 pl-2 font-mono text-sm font-bold text-accent-cyan ${extrasInSheet ? "" : "ml-auto"}`}
          >
            {lineup.team_strength}
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-white/10 text-micro font-bold text-ink-mist-dim">?</span>
          </button>
        )}
      </div>

      {lineupError && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{lineupError}</p>}

      {viewedIndex !== activeIndex && (
        <button
          onClick={() => activateMutation.mutate()}
          disabled={activateMutation.isPending}
          className="rounded-xl bg-accent-lime/10 px-3 py-2 text-center text-xs font-semibold text-accent-lime disabled:opacity-40"
        >
          {activateMutation.isPending ? "Переключаем..." : `Играть составом «${lineup?.name}»`}
        </button>
      )}

      <div
        ref={pitchRef}
        className="relative flex shrink-0 flex-col justify-between overflow-hidden rounded-[22px] bg-gradient-to-b from-[#17633a] via-[#12512f] to-[#0e4026] px-1 py-2.5 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] h-[clamp(240px,calc(100dvh-31rem),400px)] [@media(max-height:760px)]:h-[clamp(228px,calc(100dvh-29.5rem),400px)]"
      >
        <PitchBackground vivid />
        <ChemistryLinksOverlay containerRef={pitchRef} chemistry={chemistry} thin />
        {pitchRows(lineup?.formation, (lineup?.slots ?? []).map((s) => s.slot_code)).map((row) => (
          <div key={row.key} className="relative flex justify-evenly gap-0.5">
            {inRow(row, lineup?.slots ?? []).map((slot) => {
              const formationSlot = { code: slot.slot_code, category: slot.category as FormationSlot["category"], idealPosition: slot.ideal_position };
              const card = slot.card;
              return (
                <button
                  key={slot.slot_code}
                  onClick={() => setPickerSlot(formationSlot)}
                  disabled={setLineupMutation.isPending}
                  aria-label={card ? `${slot.slot_code}: ${card.player.display_name}` : `${slot.slot_code}: пусто`}
                  className="relative flex min-w-0 flex-col items-center rounded-[10px] drop-shadow-[0_3px_4px_rgba(0,30,12,0.6)] transition active:scale-95 disabled:opacity-60"
                >
                  {card ? (
                    <PitchTile
                      info={{
                        person: personKey(card.player), name: card.player.display_name, short: card.player.display_name,
                        position: card.player.position, rating: card.player.rating, club: "", country: "",
                        image: staticUrl(card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp"),
                        rarity: card.player.rarity, mine: false,
                      }}
                      anchor={slot.slot_code}
                      offPosition={!onIdealPosition(card.player.position, slot.ideal_position)}
                      frame={card.player.path_talent_code ? pathFrameClass(card.path_stage, card.prestige) : undefined}
                      chemistry={chemistryOn && chemBySlot.has(slot.slot_code) ? (
                        <ChemistryFlask
                          points={chemBySlot.get(slot.slot_code)!.points}
                          max={chemistry!.rules?.player_max ?? 3}
                          onPosition={chemBySlot.get(slot.slot_code)!.on_position}
                        />
                      ) : undefined}
                      side={
                        <ArenaTileSide
                          stars={card.stars}
                          pathStage={card.path_stage}
                          talentCode={card.player.path_talent_code ? card.talent_override || card.player.path_talent_code : null}
                          skillCode={card.skill_code}
                          skillLevel={card.skill_level}
                          skillOff={skillInactive(card.skill_code, card.player.position)}
                        />
                      }
                    />
                  ) : (
                    <div
                      data-chem-slot={slot.slot_code}
                      className="flex aspect-square w-[40px] flex-col items-center justify-center rounded-[9px] border border-dashed border-white/25 bg-black/30 min-[400px]:w-[44px]"
                    >
                      <span className="text-base leading-none text-ink-mist-dim">+</span>
                      <span className="font-mono text-[9px] leading-none text-ink-mist-dim">{slot.ideal_position}</span>
                    </div>
                  )}
                </button>
              );
            })}
            {row.category === "GK" && (
              <>
                <ArenaExtraSlot
                  side="left"
                  image={lineup?.coach ? lineup.coach.image_path : undefined}
                  filled={!!lineup?.coach}
                  label="Тренер"
                  onClick={() => setCoachPickerOpen(true)}
                  busy={setCoachMutation.isPending}
                />
                <ArenaExtraSlot
                  side="right"
                  image={lineup?.stadium ? lineup.stadium.image_path : undefined}
                  filled={!!lineup?.stadium}
                  label={lineup?.stadium?.boost_pct ? `+${Math.round(lineup.stadium.boost_pct * 100)}%` : "Стадион"}
                  onClick={() => setStadiumPickerOpen(true)}
                  busy={setStadiumMutation.isPending}
                />
              </>
            )}
          </div>
        ))}
      </div>

        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-caption font-semibold">
          <button
            onClick={() => autoFillMutation.mutate()}
            disabled={autoFillMutation.isPending}
            className="rounded-full bg-accent-lime/15 px-2.5 py-1 text-accent-lime disabled:opacity-50"
          >
            {autoFillMutation.isPending ? "Собираем..." : "Лучший состав"}
          </button>
          <span title="Диамантовые карты" className={`rounded-full px-2.5 py-1 ${diamondCount >= maxDiamond ? "bg-rarity-diamond/20 text-rarity-diamond" : "bg-white/5 text-ink-mist"}`}>
            💎 {diamondCount}/{maxDiamond}
          </span>
          <span title="Карты Академии" className={`rounded-full px-2.5 py-1 ${pathCount >= maxPath ? "bg-emerald-400/20 text-path" : "bg-white/5 text-ink-mist"}`}>
            🌱 {pathCount}/{maxPath}
          </span>
          {lineupSkills.length > 0 && (
            <button onClick={() => setSheet("skills")} className="rounded-full bg-white/5 px-2.5 py-1 text-ink-mist">
              Навыки {activeLineupSkills.length}/{lineupSkills.length} ?
            </button>
          )}
        </div>

      {!extrasInSheet && <>{styleBlock}{tipsBlock}</>}
      </ArenaSquadShell>}

      <StickyActionBar className="mt-auto">
        {stats && limitReached ? (
          <ArenaLimitPanel
            seconds={stats.retry_after_seconds}
            limit={stats.hourly_limit}
            onDone={() => queryClient.invalidateQueries({ queryKey: ["arena-stats"] })}
          />
        ) : (
          <>
            {stats && !!stats.hourly_limit && stats.hourly_left <= LOW_MATCHES_LEFT && (
              <p className="mb-1 text-center text-micro text-ink-mist-dim">Осталось на этот час: {stats.hourly_left}</p>
            )}
            <button
              ref={playRef}
              onClick={() => playMutation.mutate("ladder")}
              disabled={!activeLineup?.is_complete || playMutation.isPending || simulating}
              className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:bg-none disabled:bg-bg-raised disabled:text-ink-mist"
            >
              {playMutation.isPending || simulating ? "Идёт матч..." : !activeLineup?.is_complete ? "Собери состав, чтобы играть" : "Играть матч"}
            </button>
          </>
        )}
      </StickyActionBar>

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
                  onClick={() => { setMatchSheetOpen(false); setSquadToggled(true); }}
                  className="rounded-2xl bg-white/10 py-3 font-display text-sm font-bold text-ink-chalk active:scale-95"
                >
                  К составу
                </button>
                <button
                  onClick={() => { setMatchSheetOpen(false); setSquadToggled(false); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                  className="rounded-2xl bg-floodlight py-3 font-display text-sm font-bold text-bg-base active:scale-95"
                >
                  {limitReached ? "На главную" : "Следующий соперник"}
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
            startRevealed={matchReopened || !!match.resumed}
            actPending={actMutation.isPending}
            onAct={onAct}
            division={stats?.division}
            onFinished={() => {
              setSimulating(false);
              if (match.reward_coins > 0) {
                updateBalance((useAuthStore.getState().user?.balance ?? 0) + match.reward_coins);
              }
              queryClient.invalidateQueries({ queryKey: ["arena-stats"] });
              queryClient.invalidateQueries({ queryKey: ["arena-recent"] });
              queryClient.invalidateQueries({ queryKey: ["arena-opponent"] });
              if (match.ladder?.rewards.length) {
                const coins = match.ladder.rewards.reduce((sum, r) => sum + r.coins, 0);
                updateBalance((useAuthStore.getState().user?.balance ?? 0) + coins);
              }
              hapticNotify(match.result === "win" ? "success" : match.result === "loss" ? "error" : "warning");
              if (!matchReopened) setFinishedMatch(match);
            }}
          />
        )}
      </MatchSheet>

      {stats && templates && (
        <ArenaNewbieGuide
          targets={{ pitch: pitchRef, tactics: tacticsRef, play: playRef }}
          activeIndex={activeIndex}
          simulating={simulating || playMutation.isPending}
          finished={finishedMatch}
        />
      )}

      <ArenaSheet open={sheet === "tips"} title="Советы" onClose={() => setSheet(null)}>
        <div className="flex flex-col gap-3">
          {tipsBlock}
          <div>
            <p className="mb-1.5 text-caption font-bold text-ink-mist">Стиль этого состава</p>
            {styleBlock}
          </div>
        </div>
      </ArenaSheet>

      <ArenaSheet open={sheet === "division"} title="Дивизион" onClose={() => setSheet(null)}>
        {stats?.division && (
          <div className="flex flex-col gap-3">
            <ArenaDivisionCard division={stats.division} rank={stats.arena_rank} />
            <p className="text-center font-mono text-sm text-ink-mist">
              <span className="text-accent-green">{stats.matches_won}</span> · {stats.matches_drawn} · <span className="text-red-400">{stats.matches_lost}</span>
            </p>
          </div>
        )}
      </ArenaSheet>

      <ArenaSheet open={sheet === "cup"} title="Кубок выходных" onClose={() => setSheet(null)}>
        {stats?.cup && (
          <ArenaCupPanel
            cup={stats.cup}
            onPlay={() => { setSheet(null); playMutation.mutate("cup"); }}
            pending={playMutation.isPending || simulating || !activeLineup?.is_complete}
            limitReached={limitReached}
          />
        )}
      </ArenaSheet>

      <ArenaSheet open={sheet === "defense"} title="Тебя атаковали" onClose={() => setSheet(null)}>
        <ArenaDefenseList
          items={defenseItems ?? []}
          onRevenge={(id) => { setSheet(null); revengeMutation.mutate(id); }}
          revengePending={revengeMutation.isPending}
        />
      </ArenaSheet>

      <ArenaSheet open={sheet === "history"} title="История матчей" onClose={() => setSheet(null)}>
        {!history?.length ? (
          <EmptyState icon={IconBall} title="Матчей ещё не было" />
        ) : (
          <div className="flex flex-col gap-1.5">
            {history.slice(0, 5).map((m) => (
              <button
                key={m.id}
                onClick={() => { setSheet(null); openPlayed.mutate(m.id); }}
                disabled={openPlayed.isPending || simulating}
                className="flex items-center justify-between rounded-xl bg-white/5 px-3 py-2 text-left text-sm active:scale-[0.98]"
              >
                <span className="min-w-0 truncate text-ink-mist">{m.opponent_name}</span>
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
              </button>
            ))}
          </div>
        )}
      </ArenaSheet>

      <ArenaSheet open={sheet === "templates"} title="Составы" onClose={() => setSheet(null)}>
        <div className="flex flex-col gap-1.5">
          {(templates ?? []).map((t) => (
            <button
              key={t.template_index}
              onClick={() => { setSelectedIndex(t.template_index); setRenamingTemplate(false); setSheet(null); }}
              className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm font-semibold ${
                t.template_index === viewedIndex ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
              }`}
            >
              <span className="truncate">{t.name}</span>
              {t.is_active && <span className="text-micro font-bold">играет</span>}
            </button>
          ))}
          {renamingTemplate ? (
            <div className="flex gap-2">
              <input
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                maxLength={64}
                className="min-w-0 flex-1 rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
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
              className="py-1 text-caption font-semibold text-ink-mist-dim"
            >
              ✎ Переименовать «{lineup?.name}»
            </button>
          )}
        </div>
      </ArenaSheet>

      <ArenaSheet open={sheet === "formations"} title="Схема" onClose={() => setSheet(null)}>
        <div className="grid grid-cols-2 gap-1.5">
          {Object.keys(FORMATION_LABELS).map((code) => {
            const active = (lineup?.formation ?? "4-3-3") === code;
            return (
              <button
                key={code}
                onClick={() => { setSheet(null); if (!active) setFormationMutation.mutate(code); }}
                disabled={setFormationMutation.isPending}
                className={`rounded-xl py-2.5 text-sm font-bold disabled:opacity-60 ${active ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
              >
                {FORMATION_LABELS[code]}
              </button>
            );
          })}
        </div>
      </ArenaSheet>

      <ArenaSheet open={sheet === "skills"} title="Навыки карточек" onClose={() => setSheet(null)}>
        <div className="flex flex-col gap-2">
          <p className="text-caption leading-relaxed text-ink-mist">
            Навык усиливает одно событие в матче, рейтинг он не меняет. Работает не на всех позициях и не во всех режимах.
          </p>
          {lineupSkills.map((s) => {
            const skill = skillByCode(skillCatalog?.skills, s.card?.skill_code);
            const off = skillInactive(s.card?.skill_code, s.card?.player.position);
            return (
              <div key={s.slot_code} className="rounded-xl bg-white/5 px-3 py-2">
                <p className="flex items-center justify-between gap-2 text-sm font-semibold text-ink-chalk">
                  <span className="truncate">{s.card?.player.display_name}</span>
                  <CardSkillBadge code={s.card?.skill_code} level={s.card?.skill_level} inactiveReason={off} />
                </p>
                <p className="mt-0.5 text-caption text-ink-mist">{skill?.name}: {off ?? skill?.effect}</p>
              </div>
            );
          })}
        </div>
      </ArenaSheet>

      <ArenaSheet open={strengthHintOpen} title="Что влияет на силу" onClose={() => setStrengthHintOpen(false)}>
        <div className="flex flex-col gap-1 text-caption leading-relaxed text-ink-mist">
          {lineup?.coach && (
            <p className="text-ink-chalk">{lineup.coach.display_name}: {lineup.coach.boosts.map((b) => boostText(b)).join(" · ")}</p>
          )}
          {lineup?.stadium && (
            <p className="text-ink-chalk">
              {lineup.stadium.display_name}:{" "}
              {[
                lineup.stadium.boost_pct > 0 ? `+${Math.round(lineup.stadium.boost_pct * 100)}% к силе` : null,
                lineup.stadium.opp_malus ? `−${lineup.stadium.opp_malus} к рейтингу соперника` : null,
              ].filter(Boolean).join(" · ") || "без бонусов"}
            </p>
          )}
          <OpponentMalusNote malus={lineup?.opponent_malus} />
          <p>· Позиция: 100% рейтинга на своей, 90% на смежной, 75% не по профилю</p>
          <p>· Схема: задаёт позиции и соседей для химии, атакующие усиливают атаку, оборонительные — защиту</p>
          <p>{chemistryOn ? "· Химия: каждое очко химии игрока добавляет рейтинг в матче" : "· Химия: бонус за игроков одного клуба и страны"}</p>
          <p>· Редкость: чем выше, тем больше вклад рейтинга</p>
          <p>· Тренер: бонус к силе по редкости</p>
          <p>· Стиль: усиливает свою линию, а против стиля соперника может дать ещё бонус</p>
        </div>
      </ArenaSheet>

      {pickerSlot && (
        <CardPickerModal
          showSkills
          open
          title={`Выбери на позицию ${CATEGORY_LABELS[pickerSlot.category]}`}
          cards={cardsForSlot(pickerSlot)}
          disabledCardIds={cardsForSlot(pickerSlot)
            .filter((c) => usedPersons.includes(personKey(c.player)) || limitBlocked(c))
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

/** Coach / stadium: a corner of the goalkeeper's row. */
function ArenaExtraSlot({ side, image, filled, label, onClick, busy }: {
  side: "left" | "right";
  image?: string | null;
  filled: boolean;
  label: string;
  onClick: () => void;
  busy: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={`absolute top-0 ${side === "left" ? "left-1.5" : "right-1.5"} flex aspect-square w-[40px] flex-col items-center justify-center overflow-hidden rounded-[9px] active:scale-95 disabled:opacity-60 min-[400px]:w-[44px] ${
        filled ? "ring-1 ring-white/25" : "border border-dashed border-white/25 bg-black/30"
      }`}
    >
      {filled && (
        <img decoding="async" alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover"
          src={staticUrl(image ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")} />
      )}
      {!filled && <span className="text-base leading-none text-ink-mist-dim">+</span>}
      <span className={`${filled ? "absolute inset-x-0 bottom-0 bg-black/80 text-accent-cyan" : "text-ink-mist-dim"} text-center font-mono text-[8px] font-bold leading-[11px]`}>{label}</span>
    </button>
  );
}

const isShotMoment = (m: { kind: string }) => !["halftime", "late_call", "penalty"].includes(m.kind);

function MatchSimulation({
  match,
  actPending,
  onAct,
  onFinished,
  startRevealed = false,
  division,
}: {
  match: Match;
  actPending: boolean;
  onAct: ArenaAct;
  onFinished: () => void;
  division?: ArenaDivision | null;
  /** Reopening an already-finished match: show it as played, don't replay it. */
  startRevealed?: boolean;
}) {
  const [revealedCount, setRevealedCount] = useState(startRevealed ? match.events.length : 0);
  const [autoSkip, setAutoSkip] = useState(false);
  const [flashKey, setFlashKey] = useState(0);
  const [goalEvent, setGoalEvent] = useState<MatchEvent | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  // A reopened, already-played match must not re-credit the reward or
  // re-flash its goals.
  const finishedFiredRef = useRef(startRevealed && match.status === "finished");
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
    const upcoming = match.events[revealedCount];
    const last = revealedCount > 0 ? match.events[revealedCount - 1] : null;
    const beat = SHOT_OUTCOMES.has(upcoming?.event_type) ? SHOT_STEP_MS : QUICK_STEP_MS;
    timerRef.current = setTimeout(() => {
      if (["goal", "save", "blocked"].includes(upcoming?.event_type)) haptic("medium");
      setRevealedCount((c) => c + 1);
    }, beat + (last?.event_type === "goal" ? GOAL_HOLD_MS : 0));
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealedCount, caughtUp, isFinished, autoSkip, isBreakawayNext, total]);

  // It only announces the chance: the moment after it is on the clock.
  useEffect(() => {
    if (!isBreakawayNext || autoSkip) return undefined;
    const timer = setTimeout(() => ackBreakaway(), BREAKAWAY_HOLD_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isBreakawayNext, autoSkip, revealedCount]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [revealedCount, caughtUp, isFinished]);

  // Auto-play any pending action while skipping, so the match resolves
  // itself all the way to the final result without further input.
  useEffect(() => {
    if (!autoSkip || !caughtUp || isFinished || actPending) return;
    const pending = match.pending_moment;
    if (!pending) return;
    // The server plays it sensibly: skipping is no worse than an average choice.
    onAct("auto", { expected_seq: pending.seq });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSkip, caughtUp, isFinished, actPending, match]);

  useEffect(() => {
    if (revealedCount > prevRevealedRef.current) {
      const newly = match.events.slice(prevRevealedRef.current, revealedCount);
      if (newly.some((e) => e.event_type === "goal" && e.team === "user")) setFlashKey((k) => k + 1);
      const goal = newly.filter((e) => e.event_type === "goal").pop();
      if (goal && !autoSkip) {
        playSound(goal.team === "user" ? "goal" : "concede");
        setGoalEvent(goal);
      }
    }
    prevRevealedRef.current = revealedCount;
  }, [revealedCount, match.events, autoSkip]);

  useEffect(() => {
    if (!goalEvent) return undefined;
    const timer = setTimeout(() => setGoalEvent(null), GOAL_HOLD_MS);
    return () => clearTimeout(timer);
  }, [goalEvent]);

  const atHalftime = caughtUp && !isFinished && match.pending_moment?.kind === "halftime";
  useEffect(() => {
    if (!startRevealed && !autoSkip && (atHalftime || (caughtUp && isFinished))) playSound("whistle");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atHalftime, caughtUp, isFinished]);

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
  const pendingMoment = caughtUp && !isFinished && !autoSkip && !goalEvent ? match.pending_moment : null;
  const showFinal = caughtUp && isFinished && !goalEvent;
  const holdingBreath = !caughtUp && !autoSkip && !isBreakawayNext && SHOT_OUTCOMES.has(nextEvent?.event_type ?? "");

  // Keep the pitch on the chance the player just answered until its outcome
  // is revealed, instead of snapping back while the action request is in
  // flight and the next event waits for its reveal tick.
  const [heldMoment, setHeldMoment] = useState<{ team: string; shot_type: string; at: number } | null>(null);
  useEffect(() => {
    if (pendingMoment && isShotMoment(pendingMoment)) {
      setHeldMoment({ team: pendingMoment.team, shot_type: pendingMoment.shot_type, at: revealedCount });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingMoment?.seq]);
  const pitchMoment = (pendingMoment && isShotMoment(pendingMoment) ? pendingMoment : null)
    ?? (heldMoment && heldMoment.at === revealedCount ? heldMoment : null);

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

      {goalEvent && <ArenaGoalOverlay key={revealedCount} event={goalEvent} opponentName={match.opponent_name} />}

      <div className="flex shrink-0 items-center justify-between">
        <span className="font-mono text-xs text-ink-mist-dim">
          {showFinal ? "Матч завершён" : autoSkip ? "Пропускаем матч..." : holdingBreath ? `${currentMinute}' · удар...` : `${currentMinute}' · идёт матч...`}
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
            <ArenaMatchReport match={match} division={division} />
            <MatchStatsTable events={match.events} opponentName={match.opponent_name} />
            <MatchSkillSummary events={match.events} />
            <MatchPathSummary match={match} />
          </div>
        ) : (
          <div className="mx-auto w-full" style={{ maxWidth: "46dvh" }}>
            <MatchPitchView events={revealed} opponentName={match.opponent_name} pending={pitchMoment} />
          </div>
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

      {pendingMoment?.kind === "halftime" ? (
        <ArenaHalftimePrompt match={match} pending={pendingMoment} disabled={actPending} onAct={onAct} />
      ) : pendingMoment?.kind === "late_call" ? (
        <ArenaLateCallPrompt pending={pendingMoment} disabled={actPending} onAct={onAct} />
      ) : pendingMoment?.kind === "penalty" ? (
        <ArenaPenaltyScene key={pendingMoment.seq} pending={pendingMoment} onAct={onAct} />
      ) : pendingMoment ? (
        <ArenaMomentPrompt pending={pendingMoment} disabled={actPending} onAct={onAct} />
      ) : null}
    </section>
  );
}
