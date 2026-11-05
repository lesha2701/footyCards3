import { api } from "@/lib/api";
import type { QuantizedDive, QuantizedSwipe } from "@/lib/freeKick3d/trajectory";
import type { EpisodeTimeline } from "@/lib/oneOnOne/engine";
import type {
  FreeKick3DRefill,
  FreeKickChallenge,
  FreeKickChallengeShot,
  FreeKickChallengeStart,
  Penalty3DResult,
  Penalty3DStartResult,
  StarsInvoiceCreate,
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
  OneOnOneClaimResult,
  OneOnOneResult,
  OneOnOneStartResult,
  OtvetkaResult,
  OtvetkaStartResult,
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

/** «Испытание дня»: today's board, the player's attempt (start or pick up)
 * and a swipe of it — replayed on the server like the series'. */
export async function fetchFreeKickChallenge(): Promise<FreeKickChallenge> {
  const { data } = await api.get<FreeKickChallenge>("/games/free-kick-3d/challenge");
  return data;
}

export async function startFreeKickChallenge(): Promise<FreeKickChallengeStart> {
  const { data } = await api.post<FreeKickChallengeStart>("/games/free-kick-3d/challenge/start");
  return data;
}

export async function shootFreeKickChallenge(sessionId: number, swipe: QuantizedSwipe): Promise<FreeKickChallengeShot> {
  const { data } = await api.post<FreeKickChallengeShot>(`/games/free-kick-3d/challenge/${sessionId}/shot`, {
    dx: swipe.dx,
    dy: swipe.dy,
    curve: swipe.curve,
    duration_ms: swipe.durationMs,
  });
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

export async function fetchFreeKickRefill(): Promise<FreeKick3DRefill> {
  const { data } = await api.get<FreeKick3DRefill>("/games/free-kick-3d/refill");
  return data;
}

/** The day's first refill, paid in coins. */
export async function refillFreeKickWithCoins(): Promise<FreeKick3DRefill> {
  const { data } = await api.post<FreeKick3DRefill>("/games/free-kick-3d/refill");
  return data;
}

/** The following refills: a Telegram Stars invoice (pay via payShopWithStars). */
export async function createFreeKickRefillInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/games/free-kick-3d/refill/stars-invoice");
  return data;
}

export async function startPenalty3D(userCardId: number): Promise<Penalty3DStartResult> {
  const { data } = await api.post<Penalty3DStartResult>("/games/penalty-3d/start", { user_card_id: userCardId });
  return data;
}

/** The player's penalty: the swipe exactly as quantized for the engine. */
export async function shootPenalty3D(sessionId: number, swipe: QuantizedSwipe): Promise<Penalty3DResult> {
  const { data } = await api.post<Penalty3DResult>(`/games/penalty-3d/${sessionId}/shot`, {
    dx: swipe.dx,
    dy: swipe.dy,
    curve: swipe.curve,
    duration_ms: swipe.durationMs,
  });
  return data;
}

/** The bot's penalty: the player's dive (mm, ms from the strike), or none. */
export async function savePenalty3D(sessionId: number, dive: QuantizedDive | null): Promise<Penalty3DResult> {
  const { data } = await api.post<Penalty3DResult>(`/games/penalty-3d/${sessionId}/save`, {
    dive: dive ? { x: dive.x, y: dive.y, reaction_ms: dive.reactionMs } : null,
  });
  return data;
}

export async function claimFreeKickReward(sessionId: number): Promise<FreeKickClaimResult> {
  const { data } = await api.post<FreeKickClaimResult>(`/games/free-kick/${sessionId}/claim`);
  return data;
}

// --- «Атака 1 на 1» ---

export async function startOneOnOne(userCardId: number): Promise<OneOnOneStartResult> {
  const { data } = await api.post<OneOnOneStartResult>("/games/one-on-one/start", { user_card_id: userCardId });
  return data;
}

const timelineBody = (tl: EpisodeTimeline) => ({
  controls: tl.controls,
  feint: tl.feint,
  shot: tl.shot
    ? { tick: tl.shot.tick, dx: tl.shot.dx, dy: tl.shot.dy, curve: tl.shot.curve, duration_ms: tl.shot.durationMs }
    : null,
});

/** Only the input timeline goes up; the server replays it and decides. */
export async function playOneOnOneAttack(sessionId: number, tl: EpisodeTimeline): Promise<OneOnOneResult> {
  const { data } = await api.post<OneOnOneResult>(`/games/one-on-one/${sessionId}/attack`, timelineBody(tl));
  return data;
}

export async function claimOneOnOneReward(sessionId: number): Promise<OneOnOneClaimResult> {
  const { data } = await api.post<OneOnOneClaimResult>(`/games/one-on-one/${sessionId}/claim`);
  return data;
}

// --- «Ответка» ---

export async function startOtvetka(userCardId: number): Promise<OtvetkaStartResult> {
  const { data } = await api.post<OtvetkaStartResult>("/games/otvetka/start", { user_card_id: userCardId });
  return data;
}

/** What was done in the episode, never what came of it. */
export async function playOtvetkaEpisode(
  sessionId: number,
  body: { timeline: EpisodeTimeline } | { swipe: QuantizedSwipe },
): Promise<OtvetkaResult> {
  const payload =
    "timeline" in body
      ? { ...timelineBody(body.timeline), passes: body.timeline.passes ?? [] }
      : { swipe: { dx: body.swipe.dx, dy: body.swipe.dy, curve: body.swipe.curve, duration_ms: body.swipe.durationMs } };
  const { data } = await api.post<OtvetkaResult>(`/games/otvetka/${sessionId}/episode`, payload);
  return data;
}

export async function claimOtvetkaReward(sessionId: number): Promise<OneOnOneClaimResult> {
  const { data } = await api.post<OneOnOneClaimResult>(`/games/otvetka/${sessionId}/claim`);
  return data;
}

// --- «Ферги Тайм» ---

export async function startFergieTime(): Promise<{ session_id: number }> {
  const { data } = await api.post<{ session_id: number }>("/games/fergie-time/start");
  return data;
}

export async function finishFergieTime(sessionId: number): Promise<void> {
  await api.post(`/games/fergie-time/${sessionId}/finish`);
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
