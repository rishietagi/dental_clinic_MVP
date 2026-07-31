"""The dental chart — reading and updating a patient's mouth (step 6.11).

The **tenth `services/` module**. It holds one rule, and the rule is the reason
the chart is trustworthy:

> Marking a tooth never overwrites what was there. It supersedes it.

A tooth that was `caries` in March and `filled` in April has two rows: the March
one carrying `superseded_at = <April>`, and the April one still current. The
chart you see is `superseded_at IS NULL`; the history is everything else.

Doing it the obvious way — UPDATE the row — would silently destroy the record of
what the mouth looked like before treatment, which is exactly the thing a chart
exists to prove. It also matches how the rest of this app treats clinical data:
patients archive, catalogue items deactivate, audit rows only append.

Like the other services (the 4.3 house pattern) this raises domain exceptions
rather than `HTTPException`, and `flush()`es without committing so the router
owns the transaction.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tooth_condition import ALL_TEETH, ToothCondition


class UnknownTooth(Exception):
    """A tooth number outside FDI notation (router -> 422)."""


def current_chart(db: Session, patient_id: UUID) -> list[ToothCondition]:
    """This patient's mouth as it stands — one row per marked tooth.

    A tooth with no row is sound: a new patient has an empty chart rather than
    32 rows saying "fine", so "nothing recorded" and "examined and healthy" stay
    distinguishable.
    """
    return list(
        db.scalars(
            select(ToothCondition)
            .where(
                ToothCondition.patient_id == patient_id,
                ToothCondition.superseded_at.is_(None),
            )
            .order_by(ToothCondition.tooth)
        )
    )


def tooth_history(db: Session, patient_id: UUID, tooth: str) -> list[ToothCondition]:
    """Everything ever recorded for one tooth, oldest first."""
    return list(
        db.scalars(
            select(ToothCondition)
            .where(
                ToothCondition.patient_id == patient_id,
                ToothCondition.tooth == tooth,
            )
            .order_by(ToothCondition.recorded_at)
        )
    )


def mark_teeth(
    db: Session,
    *,
    patient_id: UUID,
    entries,  # list[schemas.chart.ToothMark]
    visit_id: UUID | None,
    actor_id: UUID | None,
) -> list[ToothCondition]:
    """Record findings, superseding whatever those teeth said before.

    Returns the newly current rows. Raises `UnknownTooth` (router -> 422).

    Only the teeth named in `entries` are touched — this is a partial update, not
    a replace-the-whole-chart, because a dentist marks the two teeth they looked
    at, and wiping the other thirty because they weren't mentioned would be a
    catastrophe dressed up as a save.

    Passing `condition=None` for a tooth **clears** it back to sound: the old row
    is superseded and no new one is inserted. That is how a mistake gets undone
    without deleting the evidence that it was recorded.
    """
    now = datetime.now(timezone.utc)

    for entry in entries:
        if entry.tooth not in ALL_TEETH:
            raise UnknownTooth(entry.tooth)

    touched = [e.tooth for e in entries]

    # Supersede the current rows for exactly these teeth, in one statement.
    existing = db.scalars(
        select(ToothCondition).where(
            ToothCondition.patient_id == patient_id,
            ToothCondition.tooth.in_(touched),
            ToothCondition.superseded_at.is_(None),
        )
    ).all()
    for row in existing:
        row.superseded_at = now

    created: list[ToothCondition] = []
    for entry in entries:
        # A null condition means "this tooth is sound again" — supersede only.
        if entry.condition is None:
            continue
        row = ToothCondition(
            patient_id=patient_id,
            tooth=entry.tooth,
            condition=entry.condition,
            surfaces=entry.surfaces,
            note=entry.note,
            recorded_visit_id=visit_id,
            recorded_by=actor_id,
            recorded_at=now,
        )
        db.add(row)
        created.append(row)

    db.flush()
    return created
