"""«Штаб»: the driver becomes the head of the transport department, the agent
seat goes to the academy director.

Revision ID: 0308
Revises: 0307
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0308"
down_revision: Union[str, None] = "0307"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One role per club (uq_manager_staff_role): the new roles are free, so a plain rename fits.
    op.execute("UPDATE manager_staff SET role = 'transport' WHERE role = 'driver'")
    op.execute("UPDATE manager_staff SET role = 'academy' WHERE role = 'agent'")


def downgrade() -> None:
    op.execute("UPDATE manager_staff SET role = 'driver' WHERE role = 'transport'")
    op.execute("UPDATE manager_staff SET role = 'agent' WHERE role = 'academy'")
