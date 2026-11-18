"""«Менеджер» — «Конфликты в штабе»: after `conflict_rounds`, when both roles
of a template (`staff_conflicts`) are held by the club's staff, the two
argue and the president decides — a «События клуба» event (code
"conflict_…", slot CONFLICT_SLOT + round) whose options move money, fans
and form like any event (manager_events.apply_choice). The assistant may
answer it like any event left open. Numbers and texts: GameConfig.manager_finance
over manager_finance.DEFAULTS."""
import random

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationType
from app.models.manager_club import ManagerClub, ManagerEvent, ManagerLeague
from app.services import manager_finance as finance, manager_staff as staff
from app.services.notification_service import notify

CONFLICT_SLOT = 200


def is_conflict(code: str) -> bool:
    return str(code or "").startswith("conflict_")


async def after_round(db: AsyncSession, club: ManagerClub, league: ManagerLeague, config) -> None:
    """The (locked) club just played: two of its staff may argue."""
    cfg = finance.cfg(config)
    if league.rounds_played not in [int(r) for r in cfg["conflict_rounds"] or []]:
        return
    owned = await staff._owned_residents(db, club.owner_id)
    names = {s.role: owned[s.resident_id].name for s in await staff.staff_of(db, club.id) if s.resident_id in owned}
    pool = [t for t in cfg["staff_conflicts"] or []
            if isinstance(t, dict) and t.get("code") and t.get("roles") and all(r in names for r in t["roles"])]
    if not pool:
        return
    t = random.Random(f"conflict:{league.id}:{club.id}:{league.rounds_played}").choice(sorted(pool, key=lambda x: x["code"]))
    roles = {r: f"{staff.ROLES[r]['name']} {names[r]}" if r in staff.ROLES else names[r] for r in t["roles"]}
    try:
        text = str(t.get("text") or "").format(**roles)
    except (KeyError, IndexError, ValueError):
        text = str(t.get("text") or "")
    options = [{**o, "label": str(o.get("label") or "").format(**roles)} if isinstance(o, dict) else o for o in t.get("options") or []]
    try:
        async with db.begin_nested():
            db.add(ManagerEvent(club_id=club.id, season_key=league.season_key, slot=CONFLICT_SLOT + league.rounds_played,
                                code=str(t["code"])[:32],
                                data={"title": t.get("title"), "text": text, "emoji": t.get("emoji", "⚡"), "options": options,
                                      "league_id": league.id, "round": league.rounds_played, "roles": t["roles"]}))
    except IntegrityError:
        return
    await notify(db, club.owner_id, NotificationType.manager_event, f"«{club.name}»: {t.get('emoji', '⚡')} {t.get('title')}",
                 "В штабе спор — нужно твоё решение", related_object_type="manager_club", related_object_id=club.id)
