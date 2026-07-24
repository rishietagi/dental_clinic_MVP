"""add consulting dentist

Revision ID: 19b4e1314059
Revises: deae87a07c3c
Create Date: 2026-07-24 06:21:06.399375

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19b4e1314059'
down_revision: Union[str, Sequence[str], None] = 'deae87a07c3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # FKs are NAMED by hand: an unnamed op.create_foreign_key(None, ...) upgrades
    # fine (Postgres invents a name) but the paired drop_constraint(None, ...) can't
    # drop an unnamed constraint, silently breaking the downgrade (the 999215bea700
    # lesson). Name them so the downgrade is reversible.
    op.add_column('appointment', sa.Column('consulting_dentist_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'appointment_consulting_dentist_id_fkey',
        'appointment', 'staff_user', ['consulting_dentist_id'], ['id'],
    )
    op.add_column('visit', sa.Column('consulting_dentist_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'visit_consulting_dentist_id_fkey',
        'visit', 'staff_user', ['consulting_dentist_id'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('visit_consulting_dentist_id_fkey', 'visit', type_='foreignkey')
    op.drop_column('visit', 'consulting_dentist_id')
    op.drop_constraint('appointment_consulting_dentist_id_fkey', 'appointment', type_='foreignkey')
    op.drop_column('appointment', 'consulting_dentist_id')
