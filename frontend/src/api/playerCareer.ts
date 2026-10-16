import type { CareerTableRow } from "@/api/career";
import type { MyPlayer } from "@/api/myPlayer";
import { api } from "@/lib/api";

export interface PlayerCareerClub {
  key: string;
  name: string;
  rating: number;
  is_demo: boolean;
  real_cards: number;
  /** Prestige the player needs to sign. */
  reputation_needed: number;
  /** null = the player may sign for this club. */
  locked_reason: string | null;
  /** Best real players of the club. */
  stars: string[];
  /** Market salary per season for this player. */
  salary: number;
  /** Division of the «Карьера тренера» club list (1 = top). */
  league: PlayerCareerLeague | null;
  level: number;
  /** Club prestige 1-5. */
  club_stars: number;
}

export interface PlayerCareerLeague {
  id: number;
  name: string;
  level: number;
}

export interface PlayerCareerOffer {
  key: string;
  name: string;
  rating: number;
  club_stars: number;
  league: string | null;
  level: number;
  salary: number;
  bonus: number;
  counters: number;
  status: "open" | "accepted" | "closed" | "withdrawn";
  /** The current club's renewal. */
  renewal: boolean;
  last: "agreed" | "walked" | null;
}

export interface PlayerCareerCupMatch {
  home: string;
  away: string;
  home_mine: boolean;
  away_mine: boolean;
  hs: number | null;
  away_score: number | null;
  pens: boolean | null;
  winner_mine: boolean | null;
  home_won: boolean | null;
}

export interface PlayerCareerCup {
  id: number;
  kind: "cl" | "national";
  title: string;
  status: "active" | "finished";
  rounds_played: number;
  next_round_at: string | null;
  alive: boolean;
  won: boolean;
  award: string | null;
  coins_earned: number;
  my_team: string | null;
  rounds: {
    label: string;
    at: string | null;
    matches: PlayerCareerCupMatch[];
    me: { played: boolean; goals: number; assists: number; rating: number | null; own: number; opp: number; pens: boolean; won: boolean; opponent: string } | null;
  }[];
}

export interface PlayerCareerGoldenBallEntry {
  place: number;
  user_id: number;
  user_name: string;
  is_me: boolean;
  matches: number;
  goals: number;
  assists: number;
  clean_sheets: number;
  line: "GK" | "DEF" | "MID" | "FWD";
  avg_rating: number | null;
  score: number;
}

export interface PlayerCareerGoldenBall {
  month: string;
  month_label: string;
  min_matches: number;
  prize_coins: number;
  prize_prestige: number;
  /** Points per goal / assist / clean sheet by line. */
  weights: Record<string, { goals: number; assists: number; clean_sheets: number }>;
  table: PlayerCareerGoldenBallEntry[];
  me: PlayerCareerGoldenBallEntry | null;
  winners: { month: string; month_label: string; user_name: string; is_me: boolean; score: number; goals: number; avg_rating: number }[];
}

export interface PlayerCareerObjective {
  code: "place" | "goals" | "clean_sheets" | "avg_rating";
  target: number;
  label: string;
  value: number;
  /** Active season: on track; finished: met. */
  met: boolean;
}

export interface PlayerCareerHistoryEntry {
  id: number;
  club: string;
  club_rating: number | null;
  place: number | null;
  matches: number;
  goals: number;
  assists: number;
  avg_rating: number | null;
  awards: string[];
  coins_earned: number;
  finished_at: string | null;
}

export interface PlayerCareerMyRound {
  played: boolean;
  goals: number;
  assists: number;
  rating: number | null;
  own: number;
  opp: number;
  opponent: string;
}

export interface PlayerCareerSeason {
  id: number;
  status: "active" | "finished" | "cancelled";
  rounds_played: number;
  total_rounds: number;
  next_round_at: string | null;
  teams: { index: number; name: string; rating: number; is_mine: boolean }[];
  table: CareerTableRow[];
  rounds: {
    index: number; at: string | null; home: number | null; away: number | null;
    hs: number | null; away_score: number | null; me: PlayerCareerMyRound | null;
  }[];
  stats: { matches: number; goals: number; assists: number; avg_rating: number | null };
  scorers: { name: string; team: string; goals: number }[];
  final_place: number | null;
  coins_earned: number;
  awards: string[];
  offers: PlayerCareerOffer[];
  league: PlayerCareerLeague | null;
  objectives: PlayerCareerObjective[];
  salary: number;
  objective_coins: number;
}

export interface PlayerCareerView {
  enabled: boolean;
  has_player: boolean;
  /** Coin balance, to refresh the top bar after a signing bonus. */
  balance?: number | null;
  player: MyPlayer | null;
  rating: number | null;
  reputation: number;
  career: { seasons: number; matches: number; goals: number; assists: number; titles: number; top_scorer: number; mvp: number } | null;
  club: PlayerCareerClub | null;
  clubs: PlayerCareerClub[];
  season: PlayerCareerSeason | null;
  can_change_club: boolean;
  rewards: {
    win: number; draw: number; goal: number; xp: number; places: number[];
    objective_coins: number; objective_rep: number;
  } | null;
  history: PlayerCareerHistoryEntry[];
  freshness: { value: number; per_match: number } | null;
  contract: { salary: number; seasons_left: number; expired: boolean; free_agent_level: number } | null;
  national: { country: string | null; prestige_needed: number; called_up: boolean } | null;
  cups: PlayerCareerCup[];
  golden_ball: PlayerCareerGoldenBall | null;
  haggle_steps: number[];
  max_counters: number;
  /** Only on the counter-offer response. */
  haggle?: { club: string; agreed: boolean; chance: number } | null;
}

export async function fetchPlayerCareer(): Promise<PlayerCareerView> {
  const { data } = await api.get<PlayerCareerView>("/player-career");
  return data;
}

export async function signPlayerCareerContract(clubKey: string): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>("/player-career/contract", { club_key: clubKey });
  return data;
}

export async function startPlayerCareerSeason(): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>("/player-career/seasons");
  return data;
}

export async function leavePlayerCareerSeason(): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>("/player-career/leave");
  return data;
}

export async function acceptPlayerCareerOffer(clubKey: string): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>(`/player-career/offers/${encodeURIComponent(clubKey)}/accept`);
  return data;
}

export async function counterPlayerCareerOffer(clubKey: string, raisePct: number): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>(`/player-career/offers/${encodeURIComponent(clubKey)}/counter`, {
    raise_pct: raisePct,
  });
  return data;
}
