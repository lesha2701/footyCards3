import { api } from "@/lib/api";
import type { MagicArmy, MagicArmyPick, MagicDifficultyCode, MagicHeal, MagicShop, MagicShopBuy, MagicHeroClassCode, MagicPackOpen,
  MagicModeCode, MagicFactionCode, MagicHub, MagicRun, StarsInvoiceCreate } from "@/types";

export async function fetchMagicHub(): Promise<MagicHub> {
  const { data } = await api.get<MagicHub>("/magic/hub");
  return data;
}

export async function fetchMagicArmy(heroClass?: MagicHeroClassCode): Promise<MagicArmy> {
  const { data } = await api.get<MagicArmy>("/magic/army", { params: { hero_class: heroClass } });
  return data;
}

export async function saveMagicArmy(stacks: MagicArmyPick[], heroClass?: MagicHeroClassCode): Promise<MagicArmy> {
  const { data } = await api.put<MagicArmy>("/magic/army", { stacks }, { params: { hero_class: heroClass } });
  return data;
}

export async function autoMagicArmy(heroClass?: MagicHeroClassCode): Promise<MagicArmy> {
  const { data } = await api.post<MagicArmy>("/magic/army/auto", null, { params: { hero_class: heroClass } });
  return data;
}

export async function startMagicRun(
  faction: MagicFactionCode, difficulty: MagicDifficultyCode, mode: MagicModeCode = "quick", challenge = false,
  heroClass: MagicHeroClassCode = "knight",
): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>("/magic/runs", { faction, difficulty, mode, challenge, hero_class: heroClass });
  return data;
}

export async function fetchMagicRun(id: number): Promise<MagicRun> {
  const { data } = await api.get<MagicRun>(`/magic/runs/${id}`);
  return data;
}

export async function magicMove(id: number, version: number, x: number, y: number): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/move`, { version, x, y });
  return data;
}

export async function magicEndDay(id: number, version: number): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/end-day`, { version });
  return data;
}

export interface MagicActInput {
  unit: string;
  action: "move" | "attack" | "shoot" | "defend" | "wait";
  target?: string | null;
  x?: number | null;
  y?: number | null;
}

export async function magicAct(id: number, version: number, input: MagicActInput): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/battle/act`, { version, ...input });
  return data;
}

export async function magicCast(id: number, version: number, spell: string, target: string | null): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/battle/cast`, { version, spell, target });
  return data;
}

export async function magicAuto(id: number, version: number): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/battle/auto`, { version });
  return data;
}

export async function magicLeaveBattle(id: number, version: number): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/battle/leave`, { version });
  return data;
}

export async function magicForfeit(id: number): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/forfeit`);
  return data;
}

export async function magicChoose(id: number, version: number, option: string): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/choose`, { version, option });
  return data;
}

export async function magicBuy(id: number, version: number, objectId: string, index: number): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/market`, { version, object_id: objectId, index });
  return data;
}

export async function magicAccept(id: number, version: number): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/accept`, { version });
  return data;
}

export async function magicRetry(id: number, version: number, pay: "coins" | "credit"): Promise<MagicRun> {
  const { data } = await api.post<MagicRun>(`/magic/runs/${id}/retry`, { version, pay });
  return data;
}

export async function magicRetryInvoice(id: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/magic/runs/${id}/retry/stars-invoice`);
  return data;
}

/** One more run of `mode` today, for coins (the day's first bought one of that mode). */
export async function buyMagicExtraRun(mode: MagicModeCode = "quick"): Promise<{ bonus_runs: number; balance: number }> {
  const { data } = await api.post<{ bonus_runs: number; balance: number }>("/magic/extra-run", null, { params: { mode } });
  return data;
}

export async function magicExtraRunInvoice(mode: MagicModeCode = "quick"): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/magic/extra-run/stars-invoice", null, { params: { mode } });
  return data;
}

export async function buyMagicCreaturePack(): Promise<MagicPackOpen> {
  const { data } = await api.post<MagicPackOpen>("/magic/creature-pack");
  return data;
}

export async function magicCreaturePackInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/magic/creature-pack/stars-invoice");
  return data;
}

export async function healMagicWounded(): Promise<MagicHeal> {
  const { data } = await api.post<MagicHeal>("/magic/heal");
  return data;
}

export async function magicHealInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/magic/heal/stars-invoice");
  return data;
}

export async function fetchMagicShop(): Promise<MagicShop> {
  const { data } = await api.get<MagicShop>("/magic/shop");
  return data;
}

export async function buyMagicShopItem(code: string): Promise<MagicShopBuy> {
  const { data } = await api.post<MagicShopBuy>("/magic/shop/buy", { code });
  return data;
}

export async function feedMagicCaptain(playerId: number, count: number): Promise<MagicArmy> {
  const { data } = await api.post<MagicArmy>(`/magic/captains/${playerId}/feed`, { count });
  return data;
}

export async function setMagicCaptainTrait(playerId: number, code: string): Promise<MagicArmy> {
  const { data } = await api.post<MagicArmy>(`/magic/captains/${playerId}/trait`, { code });
  return data;
}

export async function setMagicGuard(playerId: number): Promise<MagicArmy> {
  const { data } = await api.put<MagicArmy>("/magic/guard", { player_id: playerId });
  return data;
}

export async function refillMagicGuard(playerId: number, count: number): Promise<MagicArmy> {
  const { data } = await api.post<MagicArmy>(`/magic/guard/refill?count=${count}`, { player_id: playerId });
  return data;
}

export async function setMagicGuardTrait(code: string): Promise<MagicArmy> {
  const { data } = await api.post<MagicArmy>("/magic/guard/trait", { code });
  return data;
}

export async function reviveMagicFree(): Promise<MagicHeal> {
  const { data } = await api.post<MagicHeal>("/magic/revive");
  return data;
}
