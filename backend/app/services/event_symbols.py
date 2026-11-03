"""Limited emblem symbols of a seasonal event («Лимитка»): sold in «Менеджер»
and the clubs' emblem builder only while that event runs; whoever bought one
keeps it after. One list for both shops — the symbol's value (``img_<key>``)
maps to the event that sells it."""
from datetime import datetime
from typing import Optional

# symbol value -> event («fan_battle» | «halloween»)
EVENT_SYMBOLS: dict[str, str] = {}


def _event_module(event: str):
    from app.services import fan_battle_service, halloween_service

    return {"fan_battle": fan_battle_service, "halloween": halloween_service}.get(event)


def event_of(value: str) -> Optional[str]:
    return EVENT_SYMBOLS.get(value)


def on_sale(value: str, config, now: Optional[datetime] = None) -> bool:
    """Not a limited symbol, or its event runs now."""
    event = event_of(value)
    if event is None:
        return True
    module = _event_module(event)
    return bool(module and module.is_active(config, now))


def limited_until(value: str, config, now: Optional[datetime] = None) -> Optional[datetime]:
    """The end of the event while a limited symbol is on sale (the «до …» on its tile)."""
    event = event_of(value)
    if event is None or not on_sale(value, config, now):
        return None
    return _event_module(event).window(config)[1]
