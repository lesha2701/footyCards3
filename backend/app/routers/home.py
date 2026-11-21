"""`GET /home`: everything the Mini App asks for on its first screen, in one
request instead of ~25 parallel ones (each with its own initData check,
user load, connection and, under load, its own queue).

Each part is the very endpoint the app would call (same handler, same
response model), keyed by its path. A part that fails (404 «не в клубе»,
a feature that is off, …) is left out and listed in `errors` with its
status; the app then asks for that one itself, as before.
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.routing import APIRoute, serialize_response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import AppError
from app.database import get_db
from app.models.user import User

router = APIRouter(tags=["home"])
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
# The app's first screen: layout (top bar, banners), home, popups.
PARTS = (
    "/profile/me", "/feature-flags", "/announcement", "/maintenance", "/updates/status",
    "/my-player", "/leagues/status", "/wheel/status", "/newbie", "/starter-offer", "/presence",
    "/academy", "/matches/stats", "/career", "/club-base", "/clubs/me", "/player-tournaments/current",
    "/town", "/artifacts", "/cosmetics", "/packs/daily-offer", "/packs",
    "/streak-rewards/unseen", "/loyalty/unseen", "/comeback-gifts/unseen", "/stars-patron/letters",
    "/muses", "/halloween", "/fans", "/anniversary", "/loyalty/status", "/daily-rewards/calendar", "/tasks",
    "/free-pack/status", "/manager/summary", "/prospect", "/profile/me/attention", "/weekly-top/awards",
)
_routes: dict[str, APIRoute] = {}


def _route(request: Request, path: str) -> APIRoute | None:
    if not _routes:
        for route in request.app.routes:
            if isinstance(route, APIRoute) and "GET" in route.methods and route.path.startswith(API_PREFIX):
                _routes.setdefault(route.path[len(API_PREFIX):], route)
    route = _routes.get(path)
    # Only a plain (db, user) endpoint: anything else (a gate in its
    # dependencies, query params) stays the app's own request.
    if route is None or route.dependencies or route.dependant.query_params or route.dependant.path_params:
        return None
    if any(d.call not in (get_db, get_current_user) for d in route.dependant.dependencies):
        return None
    return route


async def _part(route: APIRoute, db: AsyncSession, user: User) -> Any:
    kwargs = {d.name: (db if d.call is get_db else user) for d in route.dependant.dependencies}
    result = await route.endpoint(**kwargs)
    return await serialize_response(
        field=route.response_field, response_content=result,
        include=route.response_model_include, exclude=route.response_model_exclude,
        by_alias=route.response_model_by_alias, exclude_unset=route.response_model_exclude_unset,
        exclude_defaults=route.response_model_exclude_defaults, exclude_none=route.response_model_exclude_none,
    )


@router.get("/home")
async def home(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    data: dict[str, Any] = {}
    errors: dict[str, int] = {}
    user_id = user.id
    for path in PARTS:
        route = _route(request, path)
        if route is None:
            errors[path] = 0
            continue
        try:
            data[path] = await _part(route, db, user)
        except AppError as exc:
            errors[path] = exc.status_code
            await db.rollback()
        except Exception:  # noqa: BLE001 — one part must not cost the whole screen
            logger.exception("home part %s failed", path)
            errors[path] = 500
            await db.rollback()
        if errors.get(path) not in (None, 0):
            # The rollback expired the user: the next part gets it fresh.
            user = await db.get(User, user_id, populate_existing=True)
    return {"data": data, "errors": errors}
