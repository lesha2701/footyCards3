import { api } from "@/lib/api";
import type {
  CardSkillState,
  SkillCatalog,
  SkillOperation,
  SkillOperationResult,
  SkillTokenBalance,
} from "@/types";

export async function fetchSkillCatalog(): Promise<SkillCatalog> {
  const { data } = await api.get<SkillCatalog>("/card-skills/catalog");
  return data;
}

export async function fetchSkillTokens(): Promise<SkillTokenBalance[]> {
  const { data } = await api.get<{ tokens: SkillTokenBalance[] }>("/card-skills/tokens");
  return data.tokens;
}

export async function fetchCardSkillState(cardId: number): Promise<CardSkillState> {
  const { data } = await api.get<CardSkillState>(`/card-skills/cards/${cardId}`);
  return data;
}

export interface SkillOperationPayload {
  operation: SkillOperation;
  skill_code?: string;
  /** The card state the player saw when confirming — the server rejects the
   * request instead of charging if it has changed since. */
  expected_skill_code: string | null;
  expected_level: number | null;
  expected_token_cost: number;
  expected_coin_cost: number;
  idempotency_key: string;
}

export async function changeCardSkill(cardId: number, payload: SkillOperationPayload): Promise<SkillOperationResult> {
  const { data } = await api.post<SkillOperationResult>(`/card-skills/cards/${cardId}`, payload);
  return data;
}
