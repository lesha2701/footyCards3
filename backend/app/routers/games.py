from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.game import (
    FreeKickClaimOut,
    FreeKickKickOut,
    FreeKickKickRequest,
    FreeKickStartOut,
    FreeKickStartRequest,
    GameLimitsOut,
    HangmanClaimOut,
    HangmanGuessOut,
    HangmanGuessRequest,
    HangmanStartOut,
    MemoryClaimOut,
    MemoryLeaderboardEntry,
    MemoryStartOut,
    MemorySubmitOut,
    MemorySubmitRequest,
    PairsClaimOut,
    PairsFlipOut,
    PairsFlipRequest,
    PairsStartOut,
    PenaltyClaimOut,
    PenaltyForfeitOut,
    PenaltyKickOut,
    PenaltyKickRequest,
    PenaltyStartOut,
    PenaltyStartRequest,
    PenaltyStatsOut,
    SaboteurClaimOut,
    SaboteurRevealOut,
    SaboteurRevealRequest,
    SaboteurStartOut,
    SaboteurStartRequest,
)
from app.schemas.fut_draft import (
    FutDraftCardArenaActionRequest,
    FutDraftClaimOut,
    FutDraftCoinFlipRequest,
    FutDraftConfigOut,
    FutDraftFormationRequest,
    FutDraftLeaderboardEntry,
    FutDraftOpenSlotRequest,
    FutDraftPenaltyKickRequest,
    FutDraftPickRequest,
    FutDraftRoundOut,
    FutDraftStartOut,
    FutDraftStateOut,
    FutDraftTacticoChoiceRequest,
)
from app.services import (
    free_kick_service,
    fut_draft_service,
    game_limits_service,
    hangman_service,
    memory_game_service,
    pairs_service,
    penalty_service,
    saboteur_service,
)
from app.services.game_config_service import get_config

router = APIRouter(prefix="/games", tags=["games"])


@router.get("/limits", response_model=GameLimitsOut)
async def get_game_limits(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    config = await get_config(db)
    return game_limits_service.get_remaining_plays(user, config)


@router.post("/memory/start", response_model=MemoryStartOut)
async def memory_start(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"memory_start:{user.id}", max_calls=20, window_seconds=60)
    return await memory_game_service.start_session(db, user)


@router.post("/memory/{session_id}/submit", response_model=MemorySubmitOut)
async def memory_submit(
    session_id: int,
    payload: MemorySubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await memory_game_service.submit_round(db, user, session_id, payload.answer)


@router.post("/memory/{session_id}/end", response_model=MemorySubmitOut)
async def memory_end(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await memory_game_service.end_session(db, user, session_id)


@router.post("/memory/{session_id}/claim", response_model=MemoryClaimOut)
async def memory_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await memory_game_service.claim_reward(db, user, session_id)


@router.get("/memory/leaderboard", response_model=list[MemoryLeaderboardEntry])
async def memory_leaderboard(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await memory_game_service.leaderboard(db)


# --- Saboteur ---

@router.post("/saboteur/start", response_model=SaboteurStartOut)
async def saboteur_start(payload: SaboteurStartRequest = SaboteurStartRequest(), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"saboteur_start:{user.id}", max_calls=20, window_seconds=60)
    return await saboteur_service.start_session(db, user, payload.steward_count)


@router.post("/saboteur/{session_id}/reveal", response_model=SaboteurRevealOut)
async def saboteur_reveal(session_id: int, payload: SaboteurRevealRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await saboteur_service.reveal_cell(db, user, session_id, payload.cell_index)


@router.post("/saboteur/{session_id}/end", response_model=SaboteurRevealOut)
async def saboteur_end(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await saboteur_service.end_session(db, user, session_id)


@router.post("/saboteur/{session_id}/claim", response_model=SaboteurClaimOut)
async def saboteur_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await saboteur_service.claim_reward(db, user, session_id)


# --- Penalty ---

@router.get("/penalty/stats", response_model=PenaltyStatsOut)
async def penalty_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_service.get_stats(db, user)


@router.post("/penalty/start", response_model=PenaltyStartOut)
async def penalty_start(payload: PenaltyStartRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"penalty_start:{user.id}", max_calls=20, window_seconds=60)
    return await penalty_service.start_session(db, user, payload.user_card_id)


@router.post("/penalty/{session_id}/kick", response_model=PenaltyKickOut)
async def penalty_kick(session_id: int, payload: PenaltyKickRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_service.resolve_kick(db, user, session_id, payload.direction)


@router.post("/penalty/{session_id}/claim", response_model=PenaltyClaimOut)
async def penalty_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_service.claim_reward(db, user, session_id)


@router.post("/penalty/{session_id}/forfeit", response_model=PenaltyForfeitOut)
async def penalty_forfeit(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_service.forfeit_session(db, user, session_id)


# --- Free Kick ---

@router.post("/free-kick/start", response_model=FreeKickStartOut)
async def free_kick_start(payload: FreeKickStartRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"free_kick_start:{user.id}", max_calls=20, window_seconds=60)
    return await free_kick_service.start_session(db, user, payload.user_card_id)


@router.post("/free-kick/{session_id}/kick", response_model=FreeKickKickOut)
async def free_kick_kick(session_id: int, payload: FreeKickKickRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await free_kick_service.resolve_kick(db, user, session_id, payload.elapsed_ms)


@router.post("/free-kick/{session_id}/claim", response_model=FreeKickClaimOut)
async def free_kick_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await free_kick_service.claim_reward(db, user, session_id)


# --- Football Hangman ---

@router.post("/hangman/start", response_model=HangmanStartOut)
async def hangman_start(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"hangman_start:{user.id}", max_calls=20, window_seconds=60)
    return await hangman_service.start_session(db, user)


@router.post("/hangman/{session_id}/guess", response_model=HangmanGuessOut)
async def hangman_guess(session_id: int, payload: HangmanGuessRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await hangman_service.guess_letter(db, user, session_id, payload.letter)


@router.post("/hangman/{session_id}/claim", response_model=HangmanClaimOut)
async def hangman_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await hangman_service.claim_reward(db, user, session_id)


# --- Найди пару (card pairs memory match) ---

@router.post("/pairs/start", response_model=PairsStartOut)
async def pairs_start(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"pairs_start:{user.id}", max_calls=20, window_seconds=60)
    return await pairs_service.start_session(db, user)


@router.post("/pairs/{session_id}/flip", response_model=PairsFlipOut)
async def pairs_flip(session_id: int, payload: PairsFlipRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await pairs_service.flip_card(db, user, session_id, payload.position)


@router.post("/pairs/{session_id}/claim", response_model=PairsClaimOut)
async def pairs_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await pairs_service.claim_reward(db, user, session_id)


# --- FUT Draft ---

@router.get("/fut-draft/config", response_model=FutDraftConfigOut)
async def fut_draft_config(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await fut_draft_service.get_public_config(db)


@router.get("/fut-draft/leaderboard", response_model=list[FutDraftLeaderboardEntry])
async def fut_draft_leaderboard(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await fut_draft_service.leaderboard(db)


@router.post("/fut-draft/start", response_model=FutDraftStartOut)
async def fut_draft_start(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"fut_draft_start:{user.id}", max_calls=20, window_seconds=60)
    return await fut_draft_service.start_draft(db, user)


@router.post("/fut-draft/{session_id}/formation", response_model=FutDraftStateOut)
async def fut_draft_choose_formation(
    session_id: int, payload: FutDraftFormationRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await fut_draft_service.choose_formation(db, user, session_id, payload.formation)


@router.post("/fut-draft/{session_id}/slot", response_model=FutDraftStateOut)
async def fut_draft_open_slot(
    session_id: int, payload: FutDraftOpenSlotRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await fut_draft_service.open_slot(db, user, session_id, payload.slot_code)


@router.post("/fut-draft/{session_id}/pick", response_model=FutDraftStateOut)
async def fut_draft_pick(
    session_id: int, payload: FutDraftPickRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await fut_draft_service.submit_pick(db, user, session_id, payload.player_id)


@router.post("/fut-draft/{session_id}/match/start", response_model=FutDraftRoundOut)
async def fut_draft_start_match(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await fut_draft_service.start_match(db, user, session_id)


@router.post("/fut-draft/{session_id}/card-arena/action", response_model=FutDraftRoundOut)
async def fut_draft_card_arena_action(
    session_id: int, payload: FutDraftCardArenaActionRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await fut_draft_service.submit_card_arena_action(db, user, session_id, payload.action)


@router.post("/fut-draft/{session_id}/tactico/phase", response_model=FutDraftRoundOut)
async def fut_draft_tactico_phase(
    session_id: int, payload: FutDraftTacticoChoiceRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await fut_draft_service.submit_tactico_phase(db, user, session_id, payload.choice)


@router.post("/fut-draft/{session_id}/penalty/kick", response_model=FutDraftRoundOut)
async def fut_draft_penalty_kick(
    session_id: int, payload: FutDraftPenaltyKickRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await fut_draft_service.submit_penalty_kick(db, user, session_id, payload.direction)


@router.post("/fut-draft/{session_id}/coin-flip", response_model=FutDraftRoundOut)
async def fut_draft_coin_flip(
    session_id: int, payload: FutDraftCoinFlipRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await fut_draft_service.submit_coin_flip(db, user, session_id, payload.choice)


@router.post("/fut-draft/{session_id}/claim", response_model=FutDraftClaimOut)
async def fut_draft_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await fut_draft_service.claim_reward(db, user, session_id)
