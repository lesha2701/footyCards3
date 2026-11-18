"""The «Воспитанник Академии» in the single-player modes Пенальти (classic and
3D), Штрафной (classic and 3D) and «Атака 1 на 1» — the same way he plays
«Ответка» (otvetka_service): instead of a card of the collection he plays at
his age-relative rating (prospect_service.otvetka_entry), the session's
`server_state` carries `"prospect": True`, and the claim gives him XP
(prospect_life.award_game). Coins, counters and engines are the card's.

The prospect modules are imported inside the functions: they import a lot
of the game services themselves.
"""

from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.user import User


async def entry(db: AsyncSession, user_id: int, user_card_id: int | None, prospect: bool) -> SimpleNamespace | None:
    """The prospect as the mode sees him (`.rating`, `.name`) when he plays,
    None when a card does; neither → «Выбери карту»."""
    if prospect:
        from app.services import prospect_service

        return await prospect_service.otvetka_entry(db, user_id)
    if user_card_id is None:
        raise ConflictError("Выбери карту")
    return None


async def award(db: AsyncSession, locked: User, state: dict, goals: int, won: bool, mode: str) -> int | None:
    """At a claim that rewards the session (the caller holds the user and
    session locks and marks it rewarded, so this runs once; the caller
    commits): his XP, None when a card played, 0 for a rewards-blocked user."""
    if not state.get("prospect"):
        return None
    if locked.game_rewards_blocked:
        return 0
    from app.services import prospect_life

    return await prospect_life.award_game(db, locked.id, goals, won, mode)
