"""add lab management

Revision ID: 6b93975ddf46
Revises: 19b4e1314059
Create Date: 2026-07-30 06:51:47.583939

Hand-edited beyond autogenerate for four things it cannot do:

1. **Sequences for the readable numbers.** `lab_case.number` and
   `appointment.number` are short human-readable ids ("L-231", "A-1042"), fed by
   dedicated Postgres sequences. Autogenerate emitted a bare NOT NULL Integer.
2. **Backfilling `appointment.number`.** Adding a NOT NULL column with no default
   to a table that already has rows FAILS. So: add it nullable, backfill every
   existing row from the sequence (ordered by created_at so the numbers read
   chronologically), then set NOT NULL.
3. **The date CHECK** (`expected_date >= sent_date`) — autogenerate never emits CHECKs.
4. **Named constraints.** `create_unique_constraint(None, ...)` upgrades fine but the
   paired `drop_constraint(None, ...)` cannot drop an unnamed constraint, silently
   breaking the downgrade (the 999215bea700 lesson). Everything is named.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b93975ddf46'
down_revision: Union[str, Sequence[str], None] = '19b4e1314059'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- sequences for the readable ids -------------------------------------
    # Start at 1001 so the very first numbers look like real reference numbers
    # (A-1001) rather than "A-1", which reads like test data to staff.
    op.execute("CREATE SEQUENCE lab_case_number_seq START 1001")
    op.execute("CREATE SEQUENCE appointment_number_seq START 1001")

    # --- lab (the vendor list) ----------------------------------------------
    op.create_table(
        'lab',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='lab_pkey'),
    )
    op.create_index(op.f('ix_lab_name'), 'lab', ['name'], unique=True)

    # --- lab_case (one item of work at a lab) -------------------------------
    op.create_table(
        'lab_case',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column(
            'number', sa.Integer(),
            server_default=sa.text("nextval('lab_case_number_seq')"), nullable=False,
        ),
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('lab_id', sa.UUID(), nullable=False),
        sa.Column('visit_id', sa.UUID(), nullable=True),
        sa.Column('appointment_id', sa.UUID(), nullable=True),
        sa.Column('sample_type', sa.Text(), nullable=False),
        sa.Column('tooth_ref', sa.Text(), nullable=True),
        sa.Column('sent_date', sa.Date(), nullable=False),
        sa.Column('expected_date', sa.Date(), nullable=True),
        sa.Column('received_date', sa.Date(), nullable=True),
        sa.Column('status', sa.Text(), server_default='sent', nullable=False),
        sa.Column('follow_up_done', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        # A case can't be expected back before it was sent. Hand-added: autogenerate
        # emits no CHECKs. NULL expected_date is fine (unknown turnaround).
        sa.CheckConstraint(
            'expected_date IS NULL OR expected_date >= sent_date',
            name='lab_case_dates_sane',
        ),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], name='lab_case_appointment_id_fkey'),
        sa.ForeignKeyConstraint(['created_by'], ['staff_user.id'], name='lab_case_created_by_fkey'),
        sa.ForeignKeyConstraint(['lab_id'], ['lab.id'], name='lab_case_lab_id_fkey'),
        sa.ForeignKeyConstraint(['patient_id'], ['patient.id'], name='lab_case_patient_id_fkey'),
        sa.ForeignKeyConstraint(['visit_id'], ['visit.id'], name='lab_case_visit_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='lab_case_pkey'),
        sa.UniqueConstraint('number', name='lab_case_number_key'),
    )
    op.create_index(op.f('ix_lab_case_patient_id'), 'lab_case', ['patient_id'], unique=False)
    # The sequence belongs to the column: dropping the table shouldn't orphan it.
    op.execute("ALTER SEQUENCE lab_case_number_seq OWNED BY lab_case.number")

    # --- appointment.number (added nullable, backfilled, then NOT NULL) -----
    op.add_column(
        'appointment',
        sa.Column(
            'number', sa.Integer(),
            server_default=sa.text("nextval('appointment_number_seq')"), nullable=True,
        ),
    )
    # Existing rows: assign numbers in creation order so they read chronologically.
    op.execute(
        """
        UPDATE appointment AS a
        SET number = s.rn
        FROM (
            SELECT id, 1000 + row_number() OVER (ORDER BY created_at, id) AS rn
            FROM appointment
        ) AS s
        WHERE a.id = s.id AND a.number IS NULL
        """
    )
    # Move the sequence past the backfilled values so new rows don't collide.
    op.execute(
        "SELECT setval('appointment_number_seq', "
        "COALESCE((SELECT MAX(number) FROM appointment), 1000) + 1, false)"
    )
    op.alter_column('appointment', 'number', nullable=False)
    op.create_unique_constraint('appointment_number_key', 'appointment', ['number'])
    op.execute("ALTER SEQUENCE appointment_number_seq OWNED BY appointment.number")


def downgrade() -> None:
    """Downgrade schema."""
    # Named constraint, so this can actually be dropped (unlike None).
    op.drop_constraint('appointment_number_key', 'appointment', type_='unique')
    op.drop_column('appointment', 'number')  # OWNED BY drops appointment_number_seq

    op.drop_index(op.f('ix_lab_case_patient_id'), table_name='lab_case')
    op.drop_table('lab_case')  # OWNED BY drops lab_case_number_seq
    op.drop_index(op.f('ix_lab_name'), table_name='lab')
    op.drop_table('lab')
