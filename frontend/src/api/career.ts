import { api } from "@/lib/api";
import type { MatchEvent, UserCard } from "@/types";

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
  my_player?: { name: string; position: string; rating: number } | null;
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

export interface CareerScouting {
  round_index: number;
  opponent_index: number;
  opponent_name: string;
  is_bot: boolean;
  strength: number | null;
  formation: string | null;
  mentality: string | null;
  playstyle: string | null;
  /** "last_match" = what they actually played last; "season_start" = their set-up before round 1. */
  source: "last_match" | "season_start";
  /** Oldest first: W / D / L. */
  form: string[];
  /** My saved style against theirs; null for seasons from before the tactics update. */
  hint: MatchupHint | null;
  win_pct: number | null;
  /** Styles that counter theirs / styles theirs counters. */
  counters: string[];
  beats: string[];
  /** Pro/legend bot: may answer my last PLAYED style with one of threat_styles. */
  adaptive: boolean;
  my_last_playstyle: string | null;
  threat_styles: string[];
}

export interface CareerFamiliarity {
  stored_pct: number;
  current_pct: number;
  max_pct: number;
  step_pct: number;
  keep_pct: number;
  last_formation: string | null;
  last_playstyle: string | null;
}

export type ScoreState = "behind" | "level" | "ahead";

export interface CareerPlanRule {
  score: ScoreState;
  margin: number;
  from_minute: number;
  mentality: string | null;
  playstyle: string | null;
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
  scouting?: CareerScouting | null;
  familiarity?: CareerFamiliarity | null;
  match_plan?: CareerPlan | null;
  plan_limits?: { rules?: number; subs?: number };
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
}): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/lineup", payload);
  return data;
}

export async function setCareerPlan(plan: CareerPlan & { round_index?: number }): Promise<CareerView> {
  const { data } = await api.put<CareerView>("/career/plan", plan);
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
}

export interface CareerAnalysis {
  playstyle: string;
  mentality: string;
  formation: string;
  opponent_playstyle: string;
  matchup: MatchupHint;
  familiarity_pct: number;
  mine: CareerPhaseStats;
  theirs: CareerPhaseStats;
  goals_mine: CareerGoalsByOrigin;
  goals_theirs: CareerGoalsByOrigin;
  instructions: { kind: "rule"; minute: number; rule: number | null; mentality: string; playstyle: string }[];
  substitutions: { kind: "sub" | "sub_skipped"; minute: number; sub: number; in?: string; out?: string; fatigue?: number }[];
  plan: CareerPlan | null;
}

export async function fetchCareerMatch(seasonId: number, round: number, match: number): Promise<CareerMatchEvents> {
  const { data } = await api.get<CareerMatchEvents>(`/career/seasons/${seasonId}/rounds/${round}/matches/${match}`);
  return data;
}
