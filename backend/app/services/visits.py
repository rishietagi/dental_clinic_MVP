"""Visit recording logic — the auto-create / auto-close rule (step 4.3).

This is the **third `services/` module** (after `audit` and `appointments`), and
it exists to hold one rule that BUILD_PLAN §3 cares about a great deal:

> Simple cases stay simple: a one-visit cleaning is a Treatment with exactly one
> Visit, auto-created and auto-closed. The receptionist never has to think about
> the word "treatment".

4.2 made `visit.treatment_id` NOT NULL so the thread is reliable. `resolve_treatment`
is what keeps that constraint *invisible*: given a stub it creates the treatment,
and given `status="completed"` it closes it in the same transaction — so recording
a cleaning is one request and leaves nothing dangling. Get this wrong and every
one-off cleaning becomes an open treatment that 4.8's "open treatments with no
next appointment" report flags as revenue walking out the door.

It raises plain domain exceptions rather than `HTTPException` so the rule can be
unit-tested without HTTP, and so the router stays the only place that decides
status codes. 4.6 (inline follow-ups) reuses this function.

`flush()`, never `commit()`: the caller owns the transaction, because a visit,
its treatment and its procedures must all land together or not at all.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.treatment import Treatment


class TreatmentNotFound(Exception):
    """The given treatment_id doesn't exist (router -> 404)."""


class TreatmentPatientMismatch(Exception):
    """The treatment belongs to a different patient (router -> 409).

    Recording a sitting against another patient's treatment would splice two
    people's clinical histories together — worth a loud failure.
    """


class TreatmentAlreadyClosed(Exception):
    """The treatment is already completed (router -> 409).

    Reopening a closed treatment is a lifecycle action (4.5), not something a
    new visit should do as a side effect.
    """


def resolve_treatment(
    db: Session,
    *,
    patient_id: UUID,
    treatment_id: UUID | None,
    stub,  # schemas.visit.TreatmentStub | None
    status: str,
) -> tuple[Treatment, bool]:
    """Return the treatment this visit belongs to, creating it if needed.

    Exactly one of `treatment_id` / `stub` must be given — the request schema
    guarantees that, so this function trusts it.

    Returns `(treatment, created)`. `created` tells the router whether to write a
    `treatment` create-audit row, so an auto-created treatment is visible in the
    audit trail rather than appearing from nowhere.

    Flushes so the treatment has an id for the visit's FK, but does NOT commit.
    """
    if treatment_id is not None:
        treatment = db.get(Treatment, treatment_id)
        if treatment is None:
            raise TreatmentNotFound()
        if treatment.patient_id != patient_id:
            raise TreatmentPatientMismatch()
        if treatment.status == "completed":
            raise TreatmentAlreadyClosed()
        created = False
    else:
        treatment = Treatment(
            patient_id=patient_id,
            title=stub.title,
            tooth_ref=stub.tooth_ref,
        )
        db.add(treatment)
        created = True

    _apply_status(treatment, status)

    # Assign the id (new treatment) / persist the status change, without
    # committing — the router commits once, atomically, at the end.
    db.flush()
    return treatment, created


def _apply_status(treatment: Treatment, status: str) -> None:
    """Set the treatment's status, keeping `closed_at` consistent with it.

    The pair (status, closed_at) is only ever changed together — a `completed`
    treatment with no `closed_at`, or an open one carrying a stale close date,
    would both make the history read wrong. `datetime.now(timezone.utc)` rather
    than a DB default because this is a business event ("the dentist declared it
    finished"), not a row-write timestamp.
    """
    if status == "completed":
        treatment.status = "completed"
        # Don't overwrite an existing close time if it's somehow already set.
        if treatment.closed_at is None:
            treatment.closed_at = datetime.now(timezone.utc)
    else:
        treatment.status = "in_progress"
        treatment.closed_at = None
