"""Who a card is: the footballer behind it. Copies and other versions of
one player (base, TOTY, legendary…) are separate Player rows, so squads
compare this key, not player_id — no XI fields three Messis.

`Player.person_key` (admin «Один футболист») ties versions written
differently («Месси» / «Лионель Месси», «Гарри» / «Харри Кейн»); empty =
the normalized display name. Namesakes (Луис / Браим Диас) stay apart."""
import re


def normalize(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).casefold().replace("ё", "е")


def person_key(player) -> str:
    return normalize(getattr(player, "person_key", None) or player.display_name)


def card_person(card) -> str:
    return person_key(card.player)
