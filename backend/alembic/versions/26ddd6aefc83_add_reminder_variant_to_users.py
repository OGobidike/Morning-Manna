"""add reminder variant to users

Revision ID: 26ddd6aefc83
Revises: 11fefea908cf
Create Date: 2026-11-02 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26ddd6aefc83'
down_revision: Union[str, Sequence[str], None] = '11fefea908cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Give every reader a reminder wording, A or B, for the reminder experiment."""
    # Empty at first, so readers who already exist can be given a group before the rule applies
    op.add_column('users', sa.Column('reminder_variant', sa.String(length=1), nullable=True))
    # Readers who joined before the experiment get a coin flip too (random() is new for each
    # row), so every reader has a group. The analysis only counts readers who sign up after
    # the experiment starts, so these early readers are never part of the result.
    op.execute(
        "update users set reminder_variant = case when random() < 0.5 then 'A' else 'B' end"
    )
    op.alter_column('users', 'reminder_variant', nullable=False)
    op.create_check_constraint(
        'users_reminder_variant_check', 'users', "reminder_variant in ('A', 'B')"
    )


def downgrade() -> None:
    """Remove the reminder wording, and the rule that came with it."""
    op.drop_constraint('users_reminder_variant_check', 'users', type_='check')
    op.drop_column('users', 'reminder_variant')
