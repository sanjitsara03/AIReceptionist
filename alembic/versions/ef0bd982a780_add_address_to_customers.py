"""add address to customers

Revision ID: ef0bd982a780
Revises: 5608798bd864
Create Date: 2026-05-28 15:22:53.414465

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef0bd982a780'
down_revision: Union[str, Sequence[str], None] = '5608798bd864'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "address")
