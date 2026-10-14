import { api } from "@/lib/api";
import type { ChemistryOut, MatchEvent, UserCard } from "@/types";

export interface CareerTeam {
  index: number;
  name: string;
  is_bot: boolean;
  user_id: number | null;
  strength: number | null;
}

export interface CareerTableRow {
  team_index: number;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  points: number;
}

export interface CareerMatch {
  home: number;
  away: number;
  hs: number | null;
  as: number | null;
  has_events: boolean;
}

export interface CareerRoundReport {
  yellow: string[];
  red: string[];
  suspended: string[];
  injured: string[];
  form_up: string[];
  form_down: string[];
}

export interface CareerRound {
  index: number;
  at: string | null;
  matches: CareerMatch[];
  /** My team's after-match report (cards, injuries, form); null if not played. */
  report: CareerRoundReport | null;
}

export interface CareerSquadCard {
  card: UserCard | null;
  /** «Мой игрок» entry (card is null for it). */
  my_player?: { name: string; position: string; rating: number; club?: string; country?: string } | null;
  card_id: number;
  fatigue: number;
  injured_rounds: number;
  suspended_rounds: number;
  yellows: number;
  /** Rating change for the next match from the last one (+1..+2 / -1). */
  form: number;
  owned: boolean;
}

export interface CareerSlot {
  code: string;
  category: "GK" | "DEF" | "MID" | "FWD";
  ideal_position: string;
}

export interface CareerDivision {
  /** 1 = the top division. */
  division: number;
  name: string;
  count: number;
  reward_pct: number;
  bot_level: string;
  bot_level_label: string;
  /** Top N places go up, bottom N go down. */
  promote: number;
  relegate: number;
}

export type MatchupHint = "advantage" | "neutral" | "disadvantage";

/** Tactical axes: direction / buildup / on_loss / on_win / block -> value. */
export type Tactic = Record<string, string>;

export interface RoleGroup {
  group: string;
  label: string;
  positions: string[];
  values: { value: string; label: string; hint: string }[];
}

export interface TacticsCatalog {
  /** Player roles per line (wingers / holding midfielder / full-backs). */
  roles?: RoleGroup[];
  axes: { key: string; label: string; values: { value: string; label: string; hint: string }[] }[];
  presets: { code: string; label: string; tactic: Tactic }[];
  interactions: { id: string; label: string; base: boolean }[];
  set_pieces?: {
    routines: { value: string; label: string }[];
    defences: { value: string; label: string }[];
    /** routine -> the defence it beats. */
    beats: Record<string, string>;
  };
}

export interface CareerSetPieces {
  corner_taker: number | null;
  free_kick_taker: number | null;
  penalty_taker: number | null;
  corner_routine: string;
  corner_defence: string;
}

export interface CareerProfile {
  division: number;
  reputation: number;
  rep_level: number;
  rep_name: string;
  rep_next_at: number | null;
  rep_floor: number;
  seasons_played: number;
  titles: number;
  promotions: number;
  objectives_met: number;
  achievements?: CareerAchievements;
}

export interface CareerAchievement {
  code: string;
  icon: string;
  title: string;
  text: string;
  unlocked_at: string | null;
}

export interface CareerTrophy {
  kind: "title" | "cup" | "promotion";
  label: string;
  division: number | null;
  season_id: number;
  at: string;
}

export interface CareerAchievements {
  items: CareerAchievement[];
  unlocked: number;
  total: number;
  /** Newest first. */
  trophies: CareerTrophy[];
  run: { wins: number; unbeaten: number; clean: number };
}

export interface CareerStar {
  player_id: number;
  name: string;
  rating: number;
  position: string;
}

export interface CareerAmbition {
  code: string;
  label: string;
  text: string;
  /** Worst place that still meets the objective. */
  place: number;
  bonus_pct: number;
  rep_success: number;
  rep_fail: number;
}

export interface CareerCupTie {
  a: number;
  b: number;
  a_name: string;
  b_name: string;
  sa: number | null;
  sb: number | null;
  /** Penalty shootout score when level after 90'. */
  pens: [number, number] | null;
  winner: number | null;
  has_events: boolean;
  mine: boolean;
}

export interface CareerCup {
  rounds: { name: string; after_round: number; at: string | null; ties: CareerCupTie[] }[];
  winner: number | null;
  status: "alive" | "out" | "winner";
  rotation: boolean;
  rewards: { winner: number; final: number; semi: number };
  rep_winner: number;
}

export interface CareerSeasonSummary {
  tactics: { preset: string; played: number; points: number; tactic: Tactic | null }[];
  duels: { id: string; label: string; attacker: "me" | "them"; applied: number; attacker_won: number }[];
  top_scorer: { name: string; goals: number } | null;
  most_minutes: { name: string; minutes: number } | null;
  most_missed: { name: string; rounds: number } | null;
}

export interface CareerOffseason {
  prev_season_id: number | null;
  prev_place: number | null;
  prev_division: CareerDivision | null;
  prev_coins: number;
  summary: CareerSeasonSummary | null;
  core_count: number;
  core_min: number;
  carried_pct: number;
  keep_pct: number;
  prev_formation: string | null;
  camp: string | null;
  camps: { code: string; label: string; hint: string }[];
  friendly: { opponent: string; home_score: number; away_score: number } | null;
  starts_at: string | null;
  /** The friend league carries over: both coaches play this season together. */
  friend_league?: boolean;
  /** The career's first season: a pre-season without last season's results or core. */
  first_season?: boolean;
}

export interface CareerCollectionCard {
  card_id: number;
  in_squad: boolean;
  card: UserCard | null;
  my_player: { name: string; position: string; rating: number; club?: string; country?: string } | null;
}

export interface CareerSquadWarning {
  /** critical = someone plays out of his line; thin = no cover left in a line. */
  level: "critical" | "thin";
  category: string;
  text: string;
}

export interface MatchupItem {
  id: string;
  label: string;
  /** Whose attack it is about, and who it helps. */
  attacker: "me" | "them";
  favours: "me" | "them";
  /** Weighted effect from my point of view (> 0 helps me). */
  value: number;
}

export interface MatchupReport {
  score: number;
  hint: MatchupHint;
  items: MatchupItem[];
}

export interface CareerScouting {
  round_index: number;
  opponent_index: number;
  opponent_name: string;
  is_bot: boolean;
  strength: number | null;
  formation: string | null;
  mentality: string | null;
  /** Their tactic and its preset code (or CUSTOM); null for old seasons / an unseen friend. */
  tactic: Tactic | null;
  preset: string | null;
  playstyle?: string | null;
  /** "last_match" = what they actually played last; "season_start" = their set-up before round 1. */
  source: "last_match" | "season_start";
  /** Oldest first: W / D / L. */
  form: string[];
  /** My saved tactic vs theirs. */
  matchup: MatchupReport | null;
  win_pct: number | null;
  /** Past meetings with this club (living league). */
  head_to_head?: { w: number; d: number; l: number; meetings: number } | null;
  /** Pro/legend bot: may answer my last PLAYED tactic — and with what. */
  adaptive: boolean;
  my_last_tactic: Tactic | null;
  threat: { preset: string; tactic: Tactic } | null;
  /** Their best outfield player (bots) and my man-marking of him this round. */
  star?: CareerStar | null;
  marking?: { round: number; marker: number; target: number; target_name: string } | null;
  /** A «Легенда» bot man-marks my own best player. */
  marks_you?: boolean;
}

export interface CareerFamiliarity {
  stored_pct: number;
  current_pct: number;
  max_pct: number;
  step_pct: number;
  /** Kept on a formation change / per changed tactical axis. */
  keep_pct: number;
  axis_keep_pct: number;
  last_formation: string | null;
  last_tactic: Tactic | null;
}

export type ScoreState = "behind" | "level" | "ahead";

export interface CareerPlanRule {
  score: ScoreState;
  margin: number;
  from_minute: number;
  mentality: string | null;
  /** Only the axes this instruction changes. */
  tactic: Tactic;
}

export interface CareerPlanSub {
  minute: number;
  /** null = the most tired outfield player. */
  slot: string | null;
  /** null = the best fit from the bench. */
  card_id: number | null;
  min_fatigue: number;
}

export interface CareerPlan {
  rules: CareerPlanRule[];
  subs: CareerPlanSub[];
}

export interface CareerSeason {
  id: number;
  status: "pending" | "active" | "finished" | "cancelled";
  difficulty: string;
  difficulty_label: string;
  rounds_played: number;
  total_rounds: number;
  schedule: string[];
  next_round_at: string | null;
  invite_expires_at: string | null;
  is_creator: boolean;
  my_status: "invited" | "accepted" | "declined" | "left";
  my_team_index: number;
  final_place: number | null;
  coins_earned: number;
  participants: { user_id: number; name: string; status: string; team_index: number }[];
  teams: CareerTeam[];
  table: CareerTableRow[];
  rounds: CareerRound[];
  squad: CareerSquadCard[];
  lineup: Record<string, number>;
  slots: CareerSlot[];
  formation: string;
  mentality: string;
  playstyle: string;
  division?: CareerDivision | null;
  /** Where the next season is played (set once finished or left). */
  next_division?: CareerDivision | null;
  /** 0 = season from before the tactics update (no plan/familiarity). */
  tactics_version?: number;
  tactic?: Tactic | null;
  squad_size?: number;
  scouting?: CareerScouting | null;
  familiarity?: CareerFamiliarity | null;
  match_plan?: CareerPlan | null;
  /** Chemistry of the XI for the next round (season's frozen rules). */
  chemistry?: ChemistryOut | null;
  set_pieces?: CareerSetPieces | null;
  squad_warnings?: CareerSquadWarning[];
  ambition?: string | null;
  ambitions?: CareerAmbition[];
  training?: string | null;
  trainings?: { code: string; label: string; hint: string }[];
  cup?: CareerCup | null;
  offseason?: CareerOffseason | null;
  summary?: CareerSeasonSummary | null;
  plan_limits?: { rules?: number; subs?: number };
  /** Player roles per line: group -> value. */
  roles?: Record<string, string>;
  /** Live match centre: my match at half-time (first half played). */
  live?: CareerLive | null;
  /** What the coach could still add to the match plan. */
  plan_hints?: { code: string; text: string }[];
}

export interface CareerLivePlayer {
  card_id: number;
  slot?: string;
  fatigue: number;
  name: string;
  position: string | null;
  rating: number | null;
}

export interface CareerHalftimeOrders {
  mentality: string | null;
  tactic: Tactic;
  subs: { out: number; in: number }[];
}

export interface CareerLive {
  round: number;
  second_half_at: string;
  home: number;
  away: number;
  home_name: string;
  away_name: string;
  hs: number;
  as: number;
  events: Record<string, unknown>[];
  my_side: "a" | "b";
  on: CareerLivePlayer[];
  bench: CareerLivePlayer[];
  subs_left: number;
  mentality: string | null;
  tactic: Tactic | null;
  orders: CareerHalftimeOrders | null;
}

export interface CareerLeaderboardRow {
  rank: number;
  user_id: number;
  name: string;
  division: number;
  division_name: string;
  reputation: number;
  level: string;
  titles: number;
  promotions: number;
  seasons: number;
  trophies: number;
  achievements: number;
  is_me: boolean;
}

export interface CareerLeaderboard {
  division: number | null;
  rows: CareerLeaderboardRow[];
  me: CareerLeaderboardRow | null;
  divisions: CareerDivision[];
}

export interface CareerView {
  enabled: boolean;
  difficulties: { code: string; label: string; reward_pct: number }[];
  place_rewards: number[];
  slots: string[];
  /** Today's round times as absolute instants — format in local time. */
  slot_times: string[];
  /** Division the next season would be played in (no manual difficulty). */
  division?: CareerDivision | null;
  divisions?: CareerDivision[];
  tactics_catalog?: TacticsCatalog | null;
  profile?: CareerProfile | null;
  season: CareerSeason | null;
  invite: { season_id: number; difficulty_label: string; from_name: string; expires_at: string | null } | null;
}

export async function fetchCareer(): Promise<CareerView> {
  const { data } = await api.get<CareerView>("/career");
  return data;
}

export async function createCareerSeason(friendId?: number): Promise<CareerView> {
  const { data } = await api.post<CareerView>("/career/seasons", { friend_id: friendId ?? null });
  return data;
}

export async function respondCareerInvite(seasonId: number, accept: boolean): Promise<CareerView> {
  const { data } = await api.post<CareerView>(`/career/seasons/${seasonId}/invite`, { accept });
  return data;
}

export async function startCareerWithoutFriend(seasonId: number): Promise<CareerView> {
  const { data } = await api.post<CareerView>(`/career/seasons/${seasonId}/start`);
  return data;
}

export async function setCareerLineup(payload: {
  slots: Record<string, number>;
  formation: string;
  mentality: string;
  playstyle: string;
  /** The round being prepared: refused (409) once it has kicked off. */
  round_index?: number;
  tactic?: Tactic;
}): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/lineup", payload);
  return data;
}

export async function setCareerAmbition(ambition: string): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/ambition", { ambition });
  return data;
}

export async function setCareerTraining(training: string | null, roundIndex?: number): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/training", { training, round_index: roundIndex ?? null });
  return data;
}

export async function setCareerSquad(cardIds: number[]): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/squad", { card_ids: cardIds });
  return data;
}

export async function setCareerCamp(camp: string | null): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/camp", { camp });
  return data;
}

export async function playCareerFriendly(): Promise<CareerView> {
  const { data } = await api.post<CareerView>("/career/friendly");
  return data;
}

export async function fetchCareerCollection(): Promise<{ squad_size: number; cards: CareerCollectionCard[] }> {
  const { data } = await api.get<{ squad_size: number; cards: CareerCollectionCard[] }>("/career/collection");
  return data;
}

export async function fetchCareerFriendly(seasonId: number): Promise<CareerMatchEvents> {
  const { data } = await api.get<CareerMatchEvents>(`/career/seasons/${seasonId}/friendly`);
  return data;
}

export async function setCareerCupRotation(rotation: boolean): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/cup", { rotation });
  return data;
}

export async function fetchCareerCupMatch(seasonId: number, round: number, tie: number): Promise<CareerMatchEvents> {
  const { data } = await api.get<CareerMatchEvents>(`/career/seasons/${seasonId}/cup/${round}/${tie}`);
  return data;
}

export async function previewCareerTactic(tactic: Tactic): Promise<MatchupReport | null> {
  const { data } = await api.post<{ matchup: MatchupReport | null }>("/career/tactics/preview", { tactic });
  return data.matchup;
}

export async function setCareerPlan(plan: CareerPlan & { round_index?: number; set_pieces?: CareerSetPieces }): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/plan", plan);
  return data;
}

export async function setCareerRoles(roles: Record<string, string | null>, roundIndex?: number): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/roles", { roles, round_index: roundIndex });
  return data;
}

export async function setCareerMarking(markerCardId: number | null, roundIndex?: number): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/marking", { marker_card_id: markerCardId, round_index: roundIndex });
  return data;
}

export async function setCareerHalftime(orders: CareerHalftimeOrders): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/halftime", orders);
  return data;
}

export async function fetchCareerLeaderboard(division?: number | null): Promise<CareerLeaderboard> {
  const { data } = await api.get<CareerLeaderboard>("/career/leaderboard", { params: division ? { division } : {} });
  return data;
}

export async function leaveCareer(): Promise<void> {
  await api.post("/career/leave");
}

export interface CareerMatchEvents {
  home_name: string;
  away_name: string;
  home_score: number;
  away_score: number;
  events: MatchEvent[];
  /** My own tactical analysis (seasons with tactics only). */
  analysis?: CareerAnalysis | null;
  /** My engine side: "a" = home, "b" = away. */
  my_side?: "a" | "b" | null;
  /** Cup tie level after 90': shootout score and kicks. */
  pens?: [number, number] | null;
  kicks?: { team: "a" | "b"; shooter: string; scored: boolean }[] | null;
}

export interface CareerPhaseStats {
  attacks: number;
  wing_attack: number;
  central_attack: number;
  recycled: number;
  advance: number;
  stall: number;
  breakdown: number;
  counters: number;
  counter_chances: number;
}

export interface CareerGoalsByOrigin {
  wing: number;
  central: number;
  counter: number;
  penalty: number;
  set_piece?: number;
}

export interface CareerSetPieceStats {
  corner: number;
  corner_goals: number;
  free_kick: number;
  free_kick_goals: number;
  penalty: number;
  penalty_goals: number;
}

export interface CareerAnalysis {
  formation: string;
  mentality: string;
  tactic: Tactic;
  preset: string;
  opponent_tactic: Tactic;
  matchup: MatchupReport;
  familiarity_pct: number;
  mine: CareerPhaseStats;
  theirs: CareerPhaseStats;
  goals_mine: CareerGoalsByOrigin;
  goals_theirs: CareerGoalsByOrigin;
  set_pieces_mine?: CareerSetPieceStats;
  set_pieces_theirs?: CareerSetPieceStats;
  chemistry?: { team: number; max: number } | null;
  /** Axis interactions that applied in duels: whose attack, how many, how many the attacker won. */
  duels: { id: string; label: string; attacker: "me" | "them"; applied: number; attacker_won: number }[];
  /** halftime = orders given in the live match centre's break. */
  instructions: { kind: "rule"; minute: number; rule: number | null; mentality: string; tactic: Tactic; halftime?: boolean }[];
  substitutions: {
    kind: "sub" | "sub_skipped"; minute: number; sub: number | null; in?: string; out?: string; fatigue?: number; halftime?: boolean;
  }[];
  plan: CareerPlan | null;
}

export async function fetchCareerMatch(seasonId: number, round: number, match: number): Promise<CareerMatchEvents> {
  const { data } = await api.get<CareerMatchEvents>(`/career/seasons/${seasonId}/rounds/${round}/matches/${match}`);
  return data;
}
