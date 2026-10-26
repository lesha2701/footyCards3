"""players.person_key («Один футболист»): versions of one player written
differently share it, so a squad can't hold two cards of one footballer
(services/player_identity.py). Empty = the normalized display name, so only
the spelling variants found on prod are set here; the admin edits the rest.
Also the art of the «Пак дебютанта» / «Твоя команда» / «Легенда дня» packs
(backend/static/packs), unless the admin already uploaded something.

Revision ID: 0210
Revises: 0209
Create Date: 2026-10-26
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0210"
down_revision: Union[str, None] = "0209"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# normalized display name -> the footballer it is
ALIASES = {
    "месси": "лионель месси",
    "мохаммед салах": "мохамед салах",
    "харри кейн": "гарри кейн",
    "киллиан мбаппе": "килиан мбаппе",
    "уильям пачо": "вильям пачо",
    "уильям салиба": "вильям салиба",
    "бруну фернандеш": "бруно фернандеш",
    "аюб буадди": "айюб буадди",
    "вальверде": "федерико вальверде",
    "кукурелья": "марк кукурелья",
    "винисиус жуниор": "винисиус",
}
PACK_ART = {"debut": "packs/debut.webp", "debut-team": "packs/debut-team.webp", "daily-legend": "packs/daily-legend.webp"}


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).casefold().replace("ё", "е")


def upgrade() -> None:
    conn = op.get_bind()
    op.add_column("players", sa.Column("person_key", sa.String(128), nullable=True))
    op.create_index("ix_players_person_key", "players", ["person_key"])
    for player_id, name in conn.execute(sa.text("SELECT id, display_name FROM players")).all():
        key = ALIASES.get(_normalize(name))
        if key:
            conn.execute(sa.text("UPDATE players SET person_key = :k WHERE id = :id"), {"k": key, "id": player_id})
    for slug, path in PACK_ART.items():
        conn.execute(sa.text(
            "UPDATE packs SET image_path = :p WHERE slug = :s AND (image_path IS NULL OR image_path = '')"
        ), {"p": path, "s": slug})


def downgrade() -> None:
    op.drop_index("ix_players_person_key", table_name="players")
    op.drop_column("players", "person_key")
