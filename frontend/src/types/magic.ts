// «Мяч и Магия» — API shapes (backend app/schemas/magic.py).
import type { RankingEntry } from "@/types";

export type MagicFactionCode = "dawn" | "ash";
export type MagicDifficultyCode = "easy" | "normal" | "hard";

export interface MagicUnit {
  code: string;
  name: string;
  tier: number;
  emoji: string;
  ranged: boolean;
  flying: boolean;
  ability_text: string;
  hp: number;
  atk: number;
  defence: number;
  dmin: number;
  dmax: number;
  spd: number;
  /** A position variant: who becomes this creature; "" — the base one. */
  note?: string;
}

export interface MagicSpell {
  code: string;
  name: string;
  cost: number;
  target: string; // ally | enemy | all_enemies
  description: string;
  level: number;
}

export interface MagicFaction {
  code: MagicFactionCode;
  name: string;
  emoji: string;
  tagline: string;
  units: MagicUnit[];
  spells: MagicSpell[];
}

export type MagicModeCode = "quick" | "hardcore" | "adventure";

export interface MagicMode {
  code: MagicModeCode;
  label: string;
  days: number;
  cells: number;
  reward_pct: number;
  pack_chance_pct: number;
  runs?: number;
  moves?: number; // the hero's moves a day (before the class bonus)
  // This mode's own runs today: free ones, bought ones waiting, the next one's price
  // (coins — the day's first bought, then Stars, stars_left more); null — not sold now.
  free_total?: number;
  free_left?: number;
  bank?: number;
  price_coins?: number | null;
  price_stars?: number | null;
  stars_left?: number;
}

export interface MagicDifficulty {
  code: MagicDifficultyCode;
  label: string;
  reward_pct: number;
  pack_chance_pct: number;
  rating_win: number;
}

export interface MagicCard {
  player_id: number;
  name: string;
  image_path: string | null;
  rarity: string;
  rating: number;
  position: string;
}

/** A stack of the army: a creature of the collection, led by a footballer captain (optional). */
export interface MagicArmyStack {
  unit: string;
  name: string;
  emoji: string;
  faction: string;
  tier: number;
  have: number;
  count: number;
  cost: number;
  unruly: boolean;
  power: number;
  captain: MagicCard | null;
  captain_level?: number;
  captain_traits?: string[];
}

export interface MagicCaptain {
  card: MagicCard;
  cap: number;
  copies: number;
  level?: number;
  xp?: number;
  next_xp?: number | null;
  traits?: string[];
  trait_slots?: number;
  dup_xp?: number;
  fed_left?: number;
}

export interface MagicTrait {
  code: string;
  emoji: string;
  name: string;
  text: string;
}

export interface MagicGuardMaterial {
  card: MagicCard;
  spare: number;
  points: number;
}

export interface MagicGuard {
  card: MagicCard | null;
  level: number;
  xp: number;
  next_xp: number | null;
  count: number;
  size: number;
  points: number;
  fighter_points: number;
  unit: string | null;
  tier: number;
  ability: string | null;
  traits: string[];
  trait_slots: number;
  materials: MagicGuardMaterial[];
}

export interface MagicRevive {
  dead: MagicCasualty[];
  essence: number;
}

export interface MagicArmyPick {
  unit: string;
  captain: number | null;
}

export interface MagicArmy {
  stacks: MagicArmyStack[];
  creatures: MagicCreature[];
  captains: MagicCaptain[];
  max_stacks: number;
  stack_cap: number;
  auto: boolean;
  hero_class: string;
  leadership: number;
  leadership_used: number;
  costs: Record<string, number>;
  guard?: MagicGuard | null;
  traits?: MagicTrait[];
  captain_xp?: number[];
  guard_xp?: number[];
}

export interface MagicCreature {
  unit: string;
  faction: string;
  name: string;
  emoji: string;
  tier: number;
  fighters: number;
}

export interface MagicCreaturePack {
  size: number;
  coins: number | null;
  stars: number | null;
  odds: Record<string, number>;
  fighters: Record<string, number>;
}

export interface MagicPackOpen {
  cards: MagicCreature[];
  creatures: MagicCreature[];
  balance: number;
}

export type MagicHeroClassCode = "knight" | "mage" | "ranger";

export interface MagicHeroClass {
  code: MagicHeroClassCode;
  name: string;
  emoji: string;
  tagline: string;
  mana: number;
  spell_power: number;
  moves: number;
}

export interface MagicHub {
  enabled: boolean;
  hero: { level: number; xp: number; level_start: number; next_level_xp: number | null; mana: number; spell_power: number };
  rating: number;
  rank: number | null;
  wins: number;
  active_run_id: number | null;
  rewarded_today: number;
  daily_limit: number;
  free_left: number;
  bonus_runs: number;
  extra_runs_today: number;
  extra_runs_limit: number;
  extra_price_coins: number | null;
  extra_price_stars: number | null;
  can_start: boolean;
  challenge_left?: number; // the weekly challenge: tries left today
  retry_coins: number;
  retry_stars: number;
  retries_left: number;
  retry_credits: number;
  gold_coins_pct: number;
  hero_skin: string;
  hero_class?: MagicHeroClassCode;
  castle_skin: string;
  reward_win: number;
  reward_loss: number;
  pack_name: string | null;
  days: number;
  moves_per_day: number;
  factions: MagicFaction[];
  hero_classes?: MagicHeroClass[];
  creatures?: MagicCreature[];
  creature_pack?: MagicCreaturePack | null;
  last_pack?: MagicCreature[];
  essence?: number;
  wounded?: MagicWounded[];
  heal_essence?: number;
  heal_stars?: number | null;
  risk?: MagicRisk | null;
  refill_today?: boolean;
  revive?: MagicRevive | null;
  guard?: MagicGuard | null;
  skin_classes?: Record<string, MagicHeroClassCode>;
  difficulties: MagicDifficulty[];
  modes?: MagicMode[];
  challenge?: MagicChallenge | null;
  army: MagicArmyStack[];
  leadership?: number;
  leadership_used?: number;
  leadership_by_class?: Record<string, number>;
  top: RankingEntry[];
}

export interface MagicStack {
  id: string;
  unit: string;
  unit_name: string;
  emoji: string;
  name: string;
  card: MagicCard | null;
  tier: number;
  count: number;
  max_count: number;
  hp: number;
  top_hp: number;
  atk: number;
  defence: number;
  dmin: number;
  dmax: number;
  spd: number;
  ranged: boolean;
  flying: boolean;
  ability_text: string;
  trait: string | null;
  side: string;
  x: number | null;
  y: number | null;
  effects: { code: string; label: string; turns: number }[];
  defending: boolean;
}

export interface MagicMapObject {
  id: string;
  kind: string; // castle | camp | chest | well | artifact | tribune | reinforce
  x: number;
  y: number;
  label: string;
  taken_by: "me" | "bot" | null;
  owner: string | null;
  level: number | null;
  emoji: string;
  hint: string;
  guards: string[];
  variant: string | null;
  offers: MagicOffer[];
  /** Camps: the guards against your army now — easy (green), even (yellow), hard (red). */
  danger?: "easy" | "even" | "hard" | null;
  style?: string | null; // a camp's style: mixed | archers | flyers | wall | dawn | ash | lost
}

export interface MagicOffer {
  unit: string;
  unit_name: string;
  tier: number;
  count: number;
  price: number;
  bought: boolean;
}

export type MagicBiome = "meadow" | "desert" | "snow" | "ash";

export interface MagicChallenge {
  week: string;
  ends_at: string;
  best: number | null;
  plays: number;
  top: { rank: number; name: string; score: number; me: boolean }[];
}

export interface MagicQuest {
  code: string;
  text: string;
  target: number;
  progress: number;
  done: boolean;
  failed: boolean;
}

export interface MagicPerkOption {
  code: string;
  emoji: string;
  title: string;
  text: string;
}

export interface MagicNotice {
  kind: string; // chest | well | artifact | tribune | reinforce | camp | mine | market | hired | day
  title: string;
  text: string;
  points?: number;
  gold?: number;
  artifact?: string;
  unit?: string;
  object?: string;
  lines?: string[];
  event?: string | null;
}

export interface MagicEvent {
  n: number;
  kind: string;
  src?: string;
  target?: string;
  damage?: number;
  killed?: number;
  count?: number;
  amount?: number;
  raised?: number;
  x?: number;
  y?: number;
  spell?: string;
  name?: string;
  side?: string;
  targets?: string[];
  effect?: string;
  round?: number;
  winner?: string;
  text?: string;
}

export interface MagicBattle {
  kind: string; // camp | final
  foe_name: string;
  round: number;
  max_rounds: number;
  turn_of: string | null;
  can_act: boolean;
  auto: boolean;
  can_cast: boolean;
  units: MagicStack[];
  move_cells: [number, number][];
  attack_targets: { target: string; cells: [number, number][] }[];
  shoot_targets: string[];
  foe_mana: number | null;
  winner: string | null;
  won: boolean | null;
  losses: number;
  /** Rocks and trees on the field: nobody stands there. */
  rocks?: [number, number, string][];
  pitch?: string | null; // its own painted pitch ("lair"), else the map's biome
}

export interface MagicRun {
  id: number;
  version: number;
  status: string;
  result: "win" | "loss" | null;
  phase: string; // map | choice | battle | battle_over | final_lost | finished
  faction: MagicFactionCode;
  rival: MagicFactionCode;
  difficulty: MagicDifficultyCode;
  mode?: MagicModeCode;
  day: number;
  days: number;
  score: number;
  hero: {
    x: number; y: number; moves: number; mana: number; max_mana: number; spell_power: number; level: number; morale: number;
    /** Where a long walk is heading; it goes on the next day. */
    goal?: [number, number] | null;
    gold: number;
    artifacts: { code: string; name: string; emoji: string; text: string }[];
    spells: MagicSpell[];
  };
  bot: { visible: boolean; x?: number; y?: number; gain_pct: number; trail?: [number, number][] };
  map_w: number;
  map_h: number;
  /** [half width, min x+y, max x+y] of the playable band; null — the full square. */
  map_shape?: [number, number, number] | null;
  /** The road as ordered castle-to-castle tracks (for drawing). */
  tracks?: [number, number][][];
  /** The river's cells (some past the playable band, drawn only) and the road's bridges over it. */
  river?: [number, number][];
  bridges?: [number, number][];
  biome: MagicBiome;
  blocks: [number, number, "tree" | "rock" | "mountain" | "water", number][];
  road: [number, number][];
  decor: [number, number, number][];
  seen: number[];
  seen_hex?: string[]; // the same rows as hex (exact on maps wider than 53 cells)
  objects: MagicMapObject[];
  reachable: [number, number][];
  army: MagicStack[];
  power: number;
  battle: MagicBattle | null;
  events: MagicEvent[];
  log: { kind: string; day: number; text?: string }[];
  reward_coins: number;
  rating_delta: number;
  xp_gained: number;
  level_up: boolean;
  pack_name: string | null;
  pack_cards: { name: string; rarity: string; image_path: string | null }[];
  battles_won: number;
  notice: MagicNotice | null;
  pending:
    | { kind?: undefined; object: string; options: { code: "gold" | "xp"; gold?: number; xp?: number }[] }
    | { kind: "perk"; options: MagicPerkOption[] }
    | null;
  quests?: MagicQuest[];
  event?: { code: string; icon: string; title: string; text: string } | null;
  bot_style?: { code: string; label: string; text: string } | null;
  perks?: MagicPerkOption[];
  casualties?: MagicCasualties | null;
  challenge_week?: string | null;
  retry: { coins: number | null; stars: number | null; credits: number; left: number; available: boolean } | null;
  hero_skin: string;
  hero_class?: MagicHeroClassCode;
  castle_skin: string;
  gold_coins: number;
  created_at: string;
}

export interface MagicWounded {
  unit: string;
  name: string;
  emoji: string;
  tier: number;
  count: number;
  until: string;
}

export interface MagicCasualty {
  unit: string;
  name: string;
  emoji: string;
  tier: number;
  count: number;
}

/** What a finished run cost the collection. */
export interface MagicCasualties {
  guard_lost?: number;
  captains_xp?: number;
  dead: MagicCasualty[];
  wounded: MagicCasualty[];
  essence: number;
  until: string | null;
  won_faster: boolean;
}

/** What a run may cost — shown before every start. */
export interface MagicRisk {
  dead_pct: Record<string, number>;
  wounded_hours: number;
  wounded_hours_win: number;
  essence_per_fighter: Record<number, number>;
  hardcore_essence_x: number;
}

export interface MagicHeal {
  healed: number;
  essence: number;
  creatures: MagicCreature[];
}

export interface MagicShopItem {
  code: string;
  kind: "pack" | "leadership" | "mana" | "skin";
  title: string;
  text: string;
  price: number;
  owned: number;
  max: number | null;
  available: boolean;
  skin_kind: string | null;
  style_key: string | null;
}

export interface MagicShop {
  essence: number;
  items: MagicShopItem[];
}

export interface MagicShopBuy {
  essence: number;
  item: string;
  cards: MagicCreature[];
}
