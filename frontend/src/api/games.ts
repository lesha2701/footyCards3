import { api } from "@/lib/api";
import type { QuantizedSwipe } from "@/lib/freeKick3d/trajectory";
import type {
  FreeKick3DShotResult,
  FreeKick3DStartResult,
  FreeKickClaimResult,
  FreeKickKickResult,
  FreeKickStartResult,
  FutDraftClaim,
  FutDraftCoinFlipChoice,
  FutDraftConfig,
  FutDraftLeaderboardEntry,
  FutDraftRound,
  FutDraftStart,
  FutDraftState,
  GameLimits,
  HangmanClaimResult,
  HangmanGuessResult,
  HangmanStartResult,
  MatchActionKind,
  MemoryClaimResult,
  MemoryLeaderboardEntry,
  MemoryStart,
  MemorySubmitResult,
  PairsClaimResult,
  PairsFlipResult,
  PairsStartResult,
  PenaltyClaimResult,
  PenaltyDirection,
  PenaltyForfeitResult,
  PenaltyKickResult,
  PenaltyStartResult,
  PenaltyStats,
  SaboteurClaimResult,
  SaboteurRevealResult,
  SaboteurStartResult,
} from "@/types";

export async function fetchGameLimits(): Promise<GameLimits> {
  const { data } = await api.get<GameLimits>("/games/limits");
  return data;
}

/** `museDate` = today's «Свидание с музой» (an extra attempt, see api/muses). */
export async function startMemoryGame(museDate = false): Promise<MemoryStart> {
  const { data } = await api.post<MemoryStart>("/games/memory/start", undefined, { params: museDate ? { muse_date: true } : undefined });
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

export async function startSaboteur(stewardCount: number): Promise<SaboteurStartResult> {
  const { data } = await api.post<SaboteurStartResult>("/games/saboteur/start", { steward_count: stewardCount });
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

export async function forfeitPenalty(sessionId: number): Promise<PenaltyForfeitResult> {
  const { data } = await api.post<PenaltyForfeitResult>(`/games/penalty/${sessionId}/forfeit`);
  return data;
}

export async function fetchPenaltyStats(): Promise<PenaltyStats> {
  const { data } = await api.get<PenaltyStats>("/games/penalty/stats");
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

export async function startFreeKick3D(userCardId: number): Promise<FreeKick3DStartResult> {
  const { data } = await api.post<FreeKick3DStartResult>("/games/free-kick-3d/start", { user_card_id: userCardId });
  return data;
}

/** The swipe exactly as quantized for the engine — the server replays it. */
export async function shootFreeKick3D(sessionId: number, swipe: QuantizedSwipe): Promise<FreeKick3DShotResult> {
  const { data } = await api.post<FreeKick3DShotResult>(`/games/free-kick-3d/${sessionId}/shot`, {
    dx: swipe.dx,
    dy: swipe.dy,
    curve: swipe.curve,
    duration_ms: swipe.durationMs,
  });
  return data;
}

export async function claimFreeKickReward(sessionId: number): Promise<FreeKickClaimResult> {
  const { data } = await api.post<FreeKickClaimResult>(`/games/free-kick/${sessionId}/claim`);
  return data;
}

// --- Football Hangman ---

export async function startHangman(museDate = false): Promise<HangmanStartResult> {
  const { data } = await api.post<HangmanStartResult>("/games/hangman/start", undefined, { params: museDate ? { muse_date: true } : undefined });
  return data;
}

export async function guessHangmanLetter(sessionId: number, letter: string): Promise<HangmanGuessResult> {
  const { data } = await api.post<HangmanGuessResult>(`/games/hangman/${sessionId}/guess`, { letter });
  return data;
}

export async function claimHangmanReward(sessionId: number): Promise<HangmanClaimResult> {
  const { data } = await api.post<HangmanClaimResult>(`/games/hangman/${sessionId}/claim`);
  return data;
}

// --- Найди пару ---

export async function startPairs(museDate = false): Promise<PairsStartResult> {
  const { data } = await api.post<PairsStartResult>("/games/pairs/start", undefined, { params: museDate ? { muse_date: true } : undefined });
  return data;
}

export async function flipPairsCard(sessionId: number, position: number): Promise<PairsFlipResult> {
  const { data } = await api.post<PairsFlipResult>(`/games/pairs/${sessionId}/flip`, { position });
  return data;
}

export async function claimPairsReward(sessionId: number): Promise<PairsClaimResult> {
  const { data } = await api.post<PairsClaimResult>(`/games/pairs/${sessionId}/claim`);
  return data;
}

// --- FUT Draft ---

export async function fetchFutDraftConfig(): Promise<FutDraftConfig> {
  const { data } = await api.get<FutDraftConfig>("/games/fut-draft/config");
  return data;
}

export async function startFutDraft(): Promise<FutDraftStart> {
  const { data } = await api.post<FutDraftStart>("/games/fut-draft/start");
  return data;
}

export async function chooseFutDraftFormation(sessionId: number, formation: string): Promise<FutDraftState> {
  const { data } = await api.post<FutDraftState>(`/games/fut-draft/${sessionId}/formation`, { formation });
  return data;
}

export async function openFutDraftSlot(sessionId: number, slotCode: string): Promise<FutDraftState> {
  const { data } = await api.post<FutDraftState>(`/games/fut-draft/${sessionId}/slot`, { slot_code: slotCode });
  return data;
}

export async function submitFutDraftPick(sessionId: number, playerId: number): Promise<FutDraftState> {
  const { data } = await api.post<FutDraftState>(`/games/fut-draft/${sessionId}/pick`, { player_id: playerId });
  return data;
}

export async function swapFutDraftSlots(sessionId: number, slotCodeA: string, slotCodeB: string): Promise<FutDraftState> {
  const { data } = await api.post<FutDraftState>(`/games/fut-draft/${sessionId}/swap`, {
    slot_code_a: slotCodeA, slot_code_b: slotCodeB,
  });
  return data;
}

export async function startFutDraftMatch(sessionId: number): Promise<FutDraftRound> {
  const { data } = await api.post<FutDraftRound>(`/games/fut-draft/${sessionId}/match/start`);
  return data;
}

export async function submitFutDraftCardArenaAction(sessionId: number, action: MatchActionKind): Promise<FutDraftRound> {
  const { data } = await api.post<FutDraftRound>(`/games/fut-draft/${sessionId}/card-arena/action`, { action });
  return data;
}

export async function submitFutDraftTacticoPhase(sessionId: number, choice: string): Promise<FutDraftRound> {
  const { data } = await api.post<FutDraftRound>(`/games/fut-draft/${sessionId}/tactico/phase`, { choice });
  return data;
}

export async function submitFutDraftPenaltyKick(sessionId: number, direction: string): Promise<FutDraftRound> {
  const { data } = await api.post<FutDraftRound>(`/games/fut-draft/${sessionId}/penalty/kick`, { direction });
  return data;
}

export async function submitFutDraftCoinFlip(sessionId: number, choice: FutDraftCoinFlipChoice): Promise<FutDraftRound> {
  const { data } = await api.post<FutDraftRound>(`/games/fut-draft/${sessionId}/coin-flip`, { choice });
  return data;
}

export async function claimFutDraftReward(sessionId: number): Promise<FutDraftClaim> {
  const { data } = await api.post<FutDraftClaim>(`/games/fut-draft/${sessionId}/claim`);
  return data;
}

export async function fetchFutDraftLeaderboard(): Promise<FutDraftLeaderboardEntry[]> {
  const { data } = await api.get<FutDraftLeaderboardEntry[]>("/games/fut-draft/leaderboard");
  return data;
}
