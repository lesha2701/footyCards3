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
  /** The club's top legend (Hall of Fame). */
  legend: { player_name: string; goals: number; seasons: number } | null;
  /** His role there today with a new coach. */
  expected_role: "bench" | "starter";
}

export type PlayerCareerRole = "bench" | "starter" | "captain";

export interface PlayerCareerMoment {
  i: number;
  kind: "attack" | "defense" | "save";
  minute: number;
  text: string;
  status: "open" | "done";
  choice: string | null;
  hit: boolean | null;
  success: boolean | null;
  auto: boolean;
  /** chance — without a timing hit, chance_hit — with one (percent). */
  options: { code: string; label: string; chance: number; chance_hit: number }[];
}

export interface PlayerCareerEvent {
  id: number;
  code: string;
  title: string;
  text: string;
  status: string;
  choices: { key: string; label: string; effects: Partial<Record<"prestige" | "trust" | "coins" | "freshness" | "xp", number>> }[];
}

export interface PlayerCareerLegend {
  place: number;
  user_name: string;
  player_name: string;
  is_me: boolean;
  seasons: number;
  matches: number;
  goals: number;
  assists: number;
  titles: number;
}

export interface PlayerCareerShop {
  pro_stars: number;
  pro_days: number;
  pro_xp_pct: number;
  agent_stars: number;
  agent_haggle_bonus: number;
  refresh_coins: number;
  refresh_stars: number;
  heal_coins: number;
  heal_stars: number;
  save_offer_stars: number;
  /** Fast seasons are on sale (admin switch). */
  fast_enabled: boolean;
  fast_stars: number;
  fast_round_minutes: number;
  pro: boolean;
  pro_until: string | null;
  agent_credits: number;
  fast_season_credits: number;
}

export interface PlayerCareerWeeklyTask {
  code: string;
  label: string;
  target: number;
  coins: number;
  value: number;
  done: boolean;
  claimed: boolean;
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
  winners: { month: string; month_label: string; user_name: string; is_me: boolean; score: number; goals: number; assists: number; avg_rating: number }[];
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
  /** Transfer window: an agent works for it / a walked-away club was brought back. */
  agent: boolean;
  saved: boolean;
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
  role: PlayerCareerRole | null;
  role_label: string | null;
  trust: number;
  trust_starter: number;
  trust_captain: number;
  injury_rounds: number;
  pending: { round: number; deadline: string; line: string; moments: PlayerCareerMoment[] } | null;
  /** Only on the key-moment response. */
  moment_result?: { i: number; kind: string; choice: string; success: boolean; chance: number } | null;
  event: PlayerCareerEvent | null;
  news: { round: number; headline: string }[];
  legends: PlayerCareerLegend[];
  chest: { available: boolean; coins_min: number; coins_max: number; token_pct: number } | null;
  weekly: { week: string; tasks: PlayerCareerWeeklyTask[] } | null;
  shop: PlayerCareerShop | null;
  fast: boolean;
}

export interface PlayerCareerRankingEntry {
  place: number;
  user_id: number;
  user_name: string;
  is_me: boolean;
  value: number;
  matches?: number;
  player_name?: string;
}

export interface PlayerCareerRankings {
  week: string;
  scorers: PlayerCareerRankingEntry[];
  assists: PlayerCareerRankingEntry[];
  ratings: PlayerCareerRankingEntry[];
  prestige: PlayerCareerRankingEntry[];
}

export interface FriendsLeague {
  id: number;
  status: "lobby" | "active" | "finished" | "cancelled";
  is_owner: boolean;
  owner_name: string;
  rounds_played: number;
  total_rounds: number;
  next_round_at: string | null;
  members: { user_id: number; name: string; status: "invited" | "accepted" | "declined" }[];
  table: (CareerTableRow & { name: string; owner_name: string | null; is_me: boolean; is_friend: boolean })[];
  rounds: {
    index: number;
    at: string | null;
    matches: {
      home: string; away: string; home_owner: string | null; away_owner: string | null;
      derby: boolean; mine: boolean; hs?: number; away_score?: number;
    }[];
  }[];
  players: { name: string; team: string; is_me: boolean; matches: number; goals: number; assists: number; avg_rating: number | null }[];
  h2h: { name: string; won: number; drawn: number; lost: number }[];
  champion: string | null;
}

export interface FriendsLeagueView {
  league: FriendsLeague | null;
  invites: { id: number; owner_name: string }[];
  can_create: boolean;
  friends: { user_id: number; name: string; player_name: string }[];
  derby_multiplier: number;
  rewards: number[];
}

export async function fetchPlayerCareer(): Promise<PlayerCareerView> {
  const { data } = await api.get<PlayerCareerView>("/player-career");
  return data;
}

export async function signPlayerCareerContract(clubKey: string): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>("/player-career/contract", { club_key: clubKey });
  return data;
}

export async function startPlayerCareerSeason(fast = false): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>("/player-career/seasons", { fast });
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

export async function playPlayerCareerMoment(index: number, option: string, hit: boolean): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>(`/player-career/moments/${index}`, { option, hit });
  return data;
}

export async function answerPlayerCareerEvent(eventId: number, choice: string): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>(`/player-career/events/${eventId}`, { choice });
  return data;
}

export async function openPlayerCareerChest(): Promise<{
  coins: number; token: { code: string; name: string; icon: string } | null; balance: number;
}> {
  const { data } = await api.post("/player-career/chest");
  return data;
}

export async function claimPlayerCareerWeekly(code: string): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>(`/player-career/weekly/${code}/claim`);
  return data;
}

export async function fetchPlayerCareerRankings(): Promise<PlayerCareerRankings> {
  const { data } = await api.get<PlayerCareerRankings>("/player-career/rankings");
  return data;
}

export async function buyPlayerCareerWithCoins(code: "refresh" | "heal"): Promise<PlayerCareerView> {
  const { data } = await api.post<PlayerCareerView>(`/player-career/shop/${code}`);
  return data;
}

export async function fetchFriendsLeague(): Promise<FriendsLeagueView> {
  const { data } = await api.get<FriendsLeagueView>("/player-career/friends");
  return data;
}

export async function createFriendsLeague(inviteIds: number[]): Promise<FriendsLeagueView> {
  const { data } = await api.post<FriendsLeagueView>("/player-career/friends", { invite_ids: inviteIds });
  return data;
}

export async function respondFriendsLeague(leagueId: number, accept: boolean): Promise<FriendsLeagueView> {
  const { data } = await api.post<FriendsLeagueView>(`/player-career/friends/${leagueId}/respond`, { accept });
  return data;
}

export async function startFriendsLeague(leagueId: number): Promise<FriendsLeagueView> {
  const { data } = await api.post<FriendsLeagueView>(`/player-career/friends/${leagueId}/start`);
  return data;
}

export async function cancelFriendsLeague(leagueId: number): Promise<FriendsLeagueView> {
  const { data } = await api.post<FriendsLeagueView>(`/player-career/friends/${leagueId}/cancel`);
  return data;
}
