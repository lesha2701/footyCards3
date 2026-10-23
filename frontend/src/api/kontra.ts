import { api } from "@/lib/api";
import type {
  KontraArena,
  KontraBattle,
  KontraBoss,
  KontraGearList,
  KontraHub,
  KontraSquad,
  StarsInvoiceCreate,
} from "@/types";

export async function fetchKontraHub(): Promise<KontraHub> {
  const { data } = await api.get<KontraHub>("/kontra/hub");
  return data;
}

export async function fetchKontraSquad(): Promise<KontraSquad> {
  const { data } = await api.get<KontraSquad>("/kontra/squad");
  return data;
}

export async function saveKontraSquad(cards: number[], leader: number): Promise<KontraSquad> {
  const { data } = await api.put<KontraSquad>("/kontra/squad", { cards, leader });
  return data;
}

export async function autoKontraSquad(): Promise<KontraSquad> {
  const { data } = await api.post<KontraSquad>("/kontra/squad/auto");
  return data;
}

export async function fetchKontraArena(): Promise<KontraArena> {
  const { data } = await api.get<KontraArena>("/kontra/arena");
  return data;
}

export async function refreshKontraArena(): Promise<KontraArena> {
  const { data } = await api.post<KontraArena>("/kontra/arena/refresh");
  return data;
}

export async function startKontraArena(offer: number, manual: boolean): Promise<KontraBattle> {
  const { data } = await api.post<KontraBattle>("/kontra/arena/start", { offer, manual });
  return data;
}

export async function fetchKontraBoss(): Promise<KontraBoss> {
  const { data } = await api.get<KontraBoss>("/kontra/boss");
  return data;
}

export async function startKontraBoss(manual: boolean): Promise<KontraBattle> {
  const { data } = await api.post<KontraBattle>("/kontra/boss/start", { manual });
  return data;
}

export async function fetchKontraBattle(id: number): Promise<KontraBattle> {
  const { data } = await api.get<KontraBattle>(`/kontra/battles/${id}`);
  return data;
}

export async function kontraAct(id: number, version: number, unitId: string, ability: string, targetId: string | null): Promise<KontraBattle> {
  const { data } = await api.post<KontraBattle>(`/kontra/battles/${id}/act`, {
    version, unit_id: unitId, ability, target_id: targetId,
  });
  return data;
}

export async function kontraAuto(id: number, version: number): Promise<KontraBattle> {
  const { data } = await api.post<KontraBattle>(`/kontra/battles/${id}/auto`, { version });
  return data;
}

export async function kontraForfeit(id: number): Promise<KontraBattle> {
  const { data } = await api.post<KontraBattle>(`/kontra/battles/${id}/forfeit`);
  return data;
}

export async function fetchKontraGear(): Promise<KontraGearList> {
  const { data } = await api.get<KontraGearList>("/kontra/gear");
  return data;
}

export async function equipKontraGear(gearId: number, cardId: number | null): Promise<KontraGearList> {
  const { data } = await api.post<KontraGearList>(`/kontra/gear/${gearId}/equip`, { card_id: cardId });
  return data;
}

export async function buyKontraChest(): Promise<KontraGearList> {
  const { data } = await api.post<KontraGearList>("/kontra/gear/chest");
  return data;
}

export async function createKontraChestInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/kontra/gear/chest/stars-invoice");
  return data;
}
