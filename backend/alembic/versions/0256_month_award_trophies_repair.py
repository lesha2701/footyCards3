"""Month awards: give the winners a cup the award didn't leave in the cabinet.

player_career_service._grant_trophy skips silently when the definition isn't
active, while the coins, the prestige and the award row still go through —
such a winner has the prize but no cup. Inserts the missing grants; a grant
counts as present when it carries that month's label.

Revision ID: 0256
Revises: 0255
Create Date: 2026-11-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0256"
down_revision: Union[str, None] = "0255"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TROPHIES = {
    "golden_boot": ("player_career_golden_boot", "{n} голов"),
    "top_assist": ("player_career_top_assist", "{n} передач"),
    "golden_glove": ("player_career_golden_glove", "{n} сухих матчей"),
    "best_defender": ("player_career_best_defender", "индекс формы {v:g}"),
}
MONTHS = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")


def upgrade() -> None:
    bind = op.get_bind()
    definitions = dict(bind.execute(sa.text(
        "SELECT code, id FROM trophy_definitions WHERE code LIKE 'player_career_%'"
    )).fetchall())
    awards = bind.execute(sa.text(
        "SELECT month, code, user_id, value, created_at FROM player_career_month_awards WHERE user_id IS NOT NULL"
    )).fetchall()
    for month, code, user_id, value, created_at in awards:
        trophy, text = TROPHIES.get(code, (None, ""))
        definition = definitions.get(trophy)
        if definition is None:
            continue
        year, number = month.split("-")
        label = f"{MONTHS[int(number) - 1]} {year}"
        present = bind.execute(sa.text(
            "SELECT 1 FROM user_trophies WHERE user_id = :u AND trophy_definition_id = :d AND message LIKE :m LIMIT 1"
        ), {"u": user_id, "d": definition, "m": f"{label}:%"}).scalar()
        if present:
            continue
        bind.execute(sa.text(
            "INSERT INTO user_trophies (user_id, trophy_definition_id, message, granted_at) VALUES (:u, :d, :m, :at)"
        ), {"u": user_id, "d": definition, "m": f"{label}: {text.format(n=int(value), v=value)}", "at": created_at})


def downgrade() -> None:
    # The repaired cups stay.
    pass
