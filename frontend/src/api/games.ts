import { api } from "@/lib/api";
import type {
  FreeKickClaimResult,
  FreeKickKickResult,
  FreeKickStartResult,
  MemoryClaimResult,
  MemoryLeaderboardEntry,
  MemoryStart,
  MemorySubmitResult,
  PenaltyClaimResult,
  PenaltyDirection,
  PenaltyKickResult,
  PenaltyStartResult,
  SaboteurClaimResult,
  SaboteurRevealResult,
  SaboteurStartResult,
} from "@/types";

export async function startMemoryGame(): Promise<MemoryStart> {
  const { data } = await api.post<MemoryStart>("/games/memory/start");
  return data;
}

export async function submitMemoryRound(sessionId: number, answer: string[]): Promise<MemorySubmitResult> {
  const { data } = await api.post<MemorySubmitResult>(`/games/memory/${sessionId}/submit`, { answer });
  return data;
}

export async function endMemoryGame(sessionId: number): Promise<MemorySubmitResult> {
  const { data } = await api.post<MemorySubmitResult>(`/games/memory/${sessionId}/end`);
  return data;
}

export async function claimMemoryReward(sessionId: number): Promise<MemoryClaimResult> {
  const { data } = await api.post<MemoryClaimResult>(`/games/memory/${sessionId}/claim`);
  return data;
}

export async function fetchMemoryLeaderboard(): Promise<MemoryLeaderboardEntry[]> {
  const { data } = await api.get<MemoryLeaderboardEntry[]>("/games/memory/leaderboard");
  return data;
}

// --- Saboteur ---

export async function startSaboteur(bombCount: number): Promise<SaboteurStartResult> {
  const { data } = await api.post<SaboteurStartResult>("/games/saboteur/start", { bomb_count: bombCount });
  return data;
}

export async function revealSaboteurCell(sessionId: number, cellIndex: number): Promise<SaboteurRevealResult> {
  const { data } = await api.post<SaboteurRevealResult>(`/games/saboteur/${sessionId}/reveal`, { cell_index: cellIndex });
  return data;
}

export async function endSaboteur(sessionId: number): Promise<SaboteurRevealResult> {
  const { data } = await api.post<SaboteurRevealResult>(`/games/saboteur/${sessionId}/end`);
  return data;
}

export async function claimSaboteurReward(sessionId: number): Promise<SaboteurClaimResult> {
  const { data } = await api.post<SaboteurClaimResult>(`/games/saboteur/${sessionId}/claim`);
  return data;
}

// --- Penalty ---

export async function startPenalty(userCardId: number): Promise<PenaltyStartResult> {
  const { data } = await api.post<PenaltyStartResult>("/games/penalty/start", { user_card_id: userCardId });
  return data;
}

export async function kickPenalty(sessionId: number, direction: PenaltyDirection): Promise<PenaltyKickResult> {
  const { data } = await api.post<PenaltyKickResult>(`/games/penalty/${sessionId}/kick`, { direction });
  return data;
}

export async function claimPenaltyReward(sessionId: number): Promise<PenaltyClaimResult> {
  const { data } = await api.post<PenaltyClaimResult>(`/games/penalty/${sessionId}/claim`);
  return data;
}

// --- Free Kick ---

export async function startFreeKick(userCardId: number): Promise<FreeKickStartResult> {
  const { data } = await api.post<FreeKickStartResult>("/games/free-kick/start", { user_card_id: userCardId });
  return data;
}

export async function kickFreeKick(sessionId: number, elapsedMs: number): Promise<FreeKickKickResult> {
  const { data } = await api.post<FreeKickKickResult>(`/games/free-kick/${sessionId}/kick`, { elapsed_ms: elapsedMs });
  return data;
}

export async function claimFreeKickReward(sessionId: number): Promise<FreeKickClaimResult> {
  const { data } = await api.post<FreeKickClaimResult>(`/games/free-kick/${sessionId}/claim`);
  return data;
}
