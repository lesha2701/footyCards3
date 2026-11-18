import type { MyPlayerAppearance } from "@/api/myPlayer";
import { api } from "@/lib/api";
import type { StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

/** «Воспитанник Академии» (backend prospect_service): the user's own child
 * footballer, raised from 6 years old to his peak. */

export interface ProspectStage {
  code: string;
  name: string;
  emoji: string;
  about: string;
  from_age: number;
  /** Rating cap of the stage; null = the peak (last stage). */
  cap: number | null;
}

export interface ProspectMemory {
  day: string;
  code: string;
  text: string;
}

export interface Prospect {
  name: string;
  number: number;
  position: string;
  foot: "right" | "left";
  appearance: MyPlayerAppearance;
  age: number;
  age_days: number;
  days_to_birthday: number;
  stage: number;
  stage_code: string;
  rating: number;
  stage_cap: number;
  /** XP is past the stage cap: it counts once the age opens the next stage. */
  capped: boolean;
  banked_points: number;
  xp: number;
  xp_in_point: number;
  xp_per_point: number;
  /** ★1-5, null until a scout or the U-19 stage reveals it. */
  potential: number | null;
  peak: number | null;
  days_to_next_stage: number | null;
  background: string;
  accessory: string | null;
  owned_cosmetics: string[];
  stats: { matches?: number; goals?: number; wins?: number; trainings?: number };
  memories: ProspectMemory[];
  atk_def: [number, number];
  /** 1 = the first child, 2+ = «Династия». */
  generation: number;
  specs: ProspectSpec[];
  /** + peak rating: «Династия» and the owner's «Академия» levels. */
  peak_bonus: { dynasty: number; academy: number };
  /** Universal player until the coach's offer («Юноши»); position is provisional then. */
  universal: boolean;
  line: ProspectLine;
  /** Deficit bonus frozen at the position choice. */
  deficit: { line: ProspectLine; xp_pct: number; value_pct: number } | null;
}

export type ProspectLine = "GK" | "DEF" | "MID" | "FWD";

export interface ProspectPositionOption {
  position: string;
  line: ProspectLine;
  line_name: string;
  /** Drills done in this line and talents leaning to it — why the coach offers it. */
  drills: number;
  talents: string[];
  deficit: boolean;
  xp_pct: number;
  value_pct: number;
}

export interface ProspectGrowth {
  potential_max: boolean;
  streak: { every: number; current: number; ups: number; max: number };
  trial: {
    matches: number;
    wins_needed: number;
    stages: { stage: number; name: string; played: number; wins: number; status: "upcoming" | "active" | "passed" | "failed" | "missed";
      /** A story win already counted here. */
      story: boolean }[];
  };
  peak: {
    dynasty: number; dynasty_per: number; academy: number; academy_level: number; per_levels: number; next_level: number | null;
  };
}

export interface ProspectSpec {
  code: string;
  name: string;
  emoji: string;
  about: string;
  /** Talent effects in % (only on a pick option). */
  effects?: Partial<Record<"goal_pct" | "win_pct" | "match_pct" | "train_pct" | "story_pct" | "atk" | "def", number>>;
}

/** A graduate («Выпускной» done): frozen rating, plays «Менеджер». */
export interface ProspectGraduate {
  id: number;
  user_id: number;
  name: string;
  number: number;
  position: string;
  appearance: MyPlayerAppearance;
  rating: number;
  potential: number;
  generation: number;
  status: "graduate" | "retired";
  graduated_at: string | null;
  specs: ProspectSpec[];
  stats: { matches?: number; goals?: number; wins?: number; trainings?: number };
  background: string;
  owner: string | null;
}

export interface ProspectDuel {
  id: number;
  status: "open" | "done" | "expired";
  incoming: boolean;
  friend: string;
  friend_prospect: string | null;
  mine: { for: number; against: number; won: boolean } | null;
  theirs: { for: number; against: number; won: boolean } | null;
  can_play: boolean;
  /** null while open or on a draw. */
  won: boolean | null;
  expires_at: string;
}

export interface ProspectFriend {
  user_id: number;
  owner: string;
  name: string;
  rating: number;
  age: number;
  number: number;
  appearance: MyPlayerAppearance;
}

export interface ProspectWeek {
  key: string;
  days_left: number;
  prizes: number[];
  my_xp: number;
  place: number | null;
  size: number;
  top: { place: number; name: string; owner: string | null; xp: number; me: boolean }[];
}

export interface ProspectStoryOption {
  label: string;
  xp: number;
  coins: number;
  /** % of the good outcome; null = a sure thing. */
  chance: number | null;
  win_xp: number | null;
  /** The good outcome counts as a won match of the stage trial (once a stage). */
  trial: boolean;
}

export interface ProspectStory {
  code: string;
  title: string;
  text: string;
  options: ProspectStoryOption[];
}

export interface ProspectShopItem {
  code: string;
  kind: "background" | "accessory";
  name: string;
  emoji: string;
  coins: number;
  stars: number;
  owned: boolean;
  /** Seasonal item (sold only in its season). */
  season?: string | null;
}

export interface ProspectView {
  enabled: boolean;
  /** The owner's coin balance after the request. */
  balance: number;
  stages: ProspectStage[];
  positions: string[];
  appearance_options: Record<keyof MyPlayerAppearance, number>;
  days_per_year: number;
  start_age: number;
  peak_range: [number, number];
  prospect: Prospect | null;
  xp_today?: number;
  daily_xp_cap?: number;
  otvetka_xp?: { match: number; goal: number; win: number };
  match_rating?: number;
  bonus?: { academy: number; mentor: number; coach: number; deficit?: number };
  bonus_pct?: number;
  coach?: { active: boolean; until: string | null; stars: number; days: number; pct: number };
  scout?: { stars: number; revealed: boolean };
  mentor?: { card_id: number; name: string; rating: number; pct: number } | null;
  mentor_options?: { card_id: number; name: string; position: string; rating: number }[];
  training?: {
    free_available: boolean;
    extra_credits: number;
    extra_bought_today: number;
    extra_max: number;
    extra_stars: number;
    xp: number;
    streak: number;
    streak_days: number;
    streak_bonus_xp: number;
    drills: { code: string; title: string; line: ProspectLine }[];
    /** Drills of every line: what he trains decides the coach's offer. */
    universal: boolean;
  };
  growth?: ProspectGrowth;
  /** The coach's offer: shown once he reaches «Юноши» without a position. */
  position_pick?: { options: ProspectPositionOption[] } | null;
  /** A change after the choice, for Stars. */
  position_change?: { stars: number; options: string[] } | null;
  story?: ProspectStory | null;
  rival?: { name: string; rating: number; ahead: number };
  cohort?: {
    key: string;
    size: number;
    place: number | null;
    top: { place: number; user_id: number; name: string; owner: string | null; rating: number; me: boolean }[];
  };
  shop?: ProspectShopItem[];
  // prospect_life: always present.
  graduate?: ProspectGraduate | null;
  hall?: { mine: ProspectGraduate[]; top: ProspectGraduate[] };
  generations?: number;
  duels?: ProspectDuel[];
  friends?: ProspectFriend[];
  duel_rules?: { hours: number; per_day: number; win_xp: number };
  gift_stars?: { training: number; coach: number };
  graduation_coins?: number;
  /** «Династия»: + peak rating per generation, and what the next child gets. */
  dynasty_bonus?: number;
  next_dynasty_peak?: number;
  // prospect_life: with a growing child.
  spec_pick?: { options: ProspectSpec[]; number: number } | null;
  graduation?: { available: boolean; stage: string; coins: number };
  week?: ProspectWeek;
  bday?: { today: boolean; opened: boolean; stars: number; xp: number };
  game_xp?: { match: number; goal: number; win: number };
}

export interface ProspectDraft {
  name: string;
  number: number;
  foot: "right" | "left";
  appearance: MyPlayerAppearance;
}

export async function fetchProspect(): Promise<ProspectView> {
  const { data } = await api.get<ProspectView>("/prospect");
  return data;
}

export async function createProspect(draft: ProspectDraft): Promise<ProspectView> {
  const { data } = await api.post<ProspectView>("/prospect", draft);
  return data;
}

export async function updateProspect(patch: Partial<ProspectDraft>): Promise<ProspectView> {
  const { data } = await api.patch<ProspectView>("/prospect", patch);
  return data;
}

export async function chooseProspectPosition(position: string): Promise<ProspectView> {
  const { data } = await api.post<ProspectView>("/prospect/position", { position });
  return data;
}

export async function trainProspect(drill: string): Promise<{
  drill: string; grade: number; xp: number; streak_bonus: number; potential_up: boolean; view: ProspectView;
}> {
  const { data } = await api.post("/prospect/train", { drill });
  return data;
}

export async function answerProspectStory(code: string, option: number): Promise<{
  won: boolean | null; xp: number; potential_up: boolean; trial_credit: boolean; coins_spent: number; view: ProspectView;
}> {
  const { data } = await api.post("/prospect/story", { code, option });
  return data;
}

export async function setProspectMentor(cardId: number | null): Promise<ProspectView> {
  const { data } = await api.put<ProspectView>("/prospect/mentor", { card_id: cardId });
  return data;
}

export async function buyProspectCosmetic(code: string): Promise<ProspectView> {
  const { data } = await api.post<ProspectView>(`/prospect/cosmetics/${code}/buy`);
  return data;
}

export async function equipProspectCosmetic(kind: "background" | "accessory", code: string | null): Promise<ProspectView> {
  const { data } = await api.put<ProspectView>("/prospect/cosmetics/equip", { kind, code });
  return data;
}

export async function chooseProspectSpec(code: string): Promise<ProspectView> {
  const { data } = await api.post<ProspectView>("/prospect/spec", { code });
  return data;
}

export async function graduateProspect(): Promise<ProspectView> {
  const { data } = await api.post<ProspectView>("/prospect/graduate");
  return data;
}

export async function challengeProspectDuel(friendId: number): Promise<{ duel_id: number; view: ProspectView }> {
  const { data } = await api.post<{ duel_id: number; view: ProspectView }>("/prospect/duels", { friend_id: friendId });
  return data;
}

/** purchase: training | coach | scout | bday | gift:<training|coach>:<user_id> | cos:<code> | pos:<POSITION>. */
export async function createProspectInvoice(purchase: string): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/prospect/stars-invoice", { purchase });
  return data;
}

export async function fetchProspectInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/prospect/stars-invoices/${payloadToken}`);
  return data;
}
