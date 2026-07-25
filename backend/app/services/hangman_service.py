import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card_collection import CardCollection
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.player import Player
from app.models.user import User
from app.schemas.game import HangmanClaimOut, HangmanGuessOut, HangmanStartOut
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

CYRILLIC_LETTERS = set("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")

FOOTBALL_TERMS: list[str] = [
    "ПЕНАЛЬТИ", "ОФСАЙД", "УГЛОВОЙ", "АВТОГОЛ", "ХЕТТРИК", "ШТАНГА", "ПЕРЕКЛАДИНА",
    "ДЕРБИ", "ДУБЛЬ", "СВИСТОК", "ГАЗОН", "ТРАНСФЕР", "ЛЕГИОНЕР", "АУТСАЙДЕР",
    "ЧЕМПИОНАТ", "ПЛЕЙОФФ", "ТРЕНЕР", "ВРАТАРСКАЯ", "СТАДИОН", "БОЛЕЛЬЩИК",
    "СУДЬЯ", "НАВЕС", "ДРИБЛИНГ", "ФОРВАРД", "ЗАЩИТНИК", "ПОЛУЗАЩИТНИК",
    "ВРАТАРЬ", "КАПИТАН", "ТРИБУНА", "РАЗГРОМ", "ФИНТ", "ПАС", "ВБРАСЫВАНИЕ",
    "ЖЕЛТАЯ КАРТОЧКА", "КРАСНАЯ КАРТОЧКА", "ШТРАФНОЙ", "ОДИННАДЦАТИМЕТРОВЫЙ",
    "КОНТРАТАКА", "ПОЛУФИНАЛ", "ФИНАЛ", "ЦЕНТРФОРВАРД", "ЗАМЕНА",
]


def _normalize_word(raw: str) -> str:
    return raw.strip().upper()


def _mask_word(word: str, guessed: set[str]) -> list[str]:
    return [ch if (not ch.isalpha() or ch in guessed) else "_" for ch in word]


async def _pick_word(db: AsyncSession) -> tuple[str, str]:
    if random.random() < 0.5:
        result = await db.execute(
            select(Player.display_name)
            .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
            .where(Player.is_active.is_(True), (CardCollection.is_active.is_(True)) | (Player.collection_id.is_(None)))
            .order_by(func.random())
            .limit(1)
        )
        display_name = result.scalar_one_or_none()
        if display_name:
            return _normalize_word(display_name), "player"
    return _normalize_word(random.choice(FOOTBALL_TERMS)), "term"


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.hangman_attempts_reset_at) if user.hangman_attempts_reset_at else None
    if reset_day != today:
        user.hangman_rewarded_attempts_today = 0
        user.hangman_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.hangman_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.hangman_hourly_attempts = 0
        user.hangman_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User) -> HangmanStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.hangman_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.hangman_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.hangman_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)
    if locked_user.hangman_rewarded_attempts_today >= config.hangman_daily_limit:
        raise ConflictError(
            "Daily reward attempts for Football Hangman exhausted; you can still play unrewarded",
            details={"daily_limit": config.hangman_daily_limit},
        )

    word, category = await _pick_word(db)
    session = GameSession(
        user_id=locked_user.id, game_type=GameType.football_hangman, status=GameSessionStatus.in_progress,
        server_state={"word": word, "category": category, "guessed_letters": [], "wrong_letters": []},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return HangmanStartOut(
        session_id=session.id,
        category=category,
        masked_word=_mask_word(word, set()),
        max_wrong=config.hangman_max_wrong,
    )


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.football_hangman:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


async def guess_letter(db: AsyncSession, user: User, session_id: int, letter: str) -> HangmanGuessOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    normalized = letter.strip().upper()
    if len(normalized) != 1 or normalized not in CYRILLIC_LETTERS:
        raise ConflictError("Guess must be a single Cyrillic letter")

    state = dict(session.server_state)
    guessed_letters: list[str] = list(state["guessed_letters"])
    wrong_letters: list[str] = list(state["wrong_letters"])
    if normalized in guessed_letters:
        raise ConflictError("Letter already guessed")

    word: str = state["word"]
    guessed_letters.append(normalized)
    is_correct = normalized in word
    if not is_correct:
        wrong_letters.append(normalized)

    state["guessed_letters"] = guessed_letters
    state["wrong_letters"] = wrong_letters
    session.server_state = state

    masked = _mask_word(word, set(guessed_letters))
    won = "_" not in masked
    lost = len(wrong_letters) >= config.hangman_max_wrong

    if won:
        session.status = GameSessionStatus.won
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = config.hangman_reward_correct
    elif lost:
        session.status = GameSessionStatus.lost
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = 0

    db.add(session)
    await db.commit()

    return HangmanGuessOut(
        session_id=session.id,
        masked_word=masked,
        guessed_letters=guessed_letters,
        wrong_letters=wrong_letters,
        max_wrong=config.hangman_max_wrong,
        status=session.status.value,
        is_correct=is_correct,
        word=word if (won or lost) else None,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> HangmanClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status not in (GameSessionStatus.lost, GameSessionStatus.won):
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    if locked_user.hangman_rewarded_attempts_today >= config.hangman_daily_limit:
        raise ConflictError("Daily reward attempts for Football Hangman exhausted")

    reward = 0 if locked_user.game_rewards_blocked else session.reward_coins
    session.is_rewarded = True
    locked_user.hangman_rewarded_attempts_today += 1

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.game_reward,
            "Награда за Футбольную виселицу", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked_user)

    return HangmanClaimOut(reward_coins=reward, new_balance=locked_user.balance)
