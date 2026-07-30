"""Lab-case logic (step 6.6) — the **ninth `services/` module**.

Holds the rules for work sent out to a dental lab: creating a case, marking it back,
cancelling it, and the dashboard bucketing that makes a forgotten case visible.

Two things worth stating, because they're the design decisions this module encodes:

**1. The wait lives here, not on the appointment.** When a sample goes out, the
appointment still closes normally (`done`) — that sitting happened, and an appointment
is a calendar slot, so holding it open would make the calendar claim the dentist is
busy on a past day. The `treatment` stays `in_progress`, so the patient still shows on
the follow-up report; this module tracks the lab side.

**2. "Today" is the CLINIC's today.** Overdue/due-soon compare `expected_date` against
the clinic-local date (via `clinic_settings.timezone`), not the server's — the same
rule the appointment day bounds and collections follow (4.9 / 5.5). A clinic in IST
must not see a case flip to "overdue" because a UTC server rolled past midnight.

Like the other services this raises **domain exceptions**, not `HTTPException`, so the
rules are unit-testable without HTTP and the router owns status codes (the 4.3
pattern). It `flush()`es but never commits — the router owns the transaction.
"""

from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.clinic_settings import ClinicSettings
from app.models.lab import Lab
from app.models.lab_case import LabCase
from app.models.patient import Patient
from app.models.visit import Visit


class PatientNotFound(Exception):
    """No patient with that id (router -> 404)."""


class LabNotFound(Exception):
    """No lab with that id (router -> 404)."""


class VisitNotFound(Exception):
    """No visit with that id (router -> 404)."""


class AppointmentNotFound(Exception):
    """No appointment with that id (router -> 404)."""


class LabCaseNotFound(Exception):
    """No lab case with that id (router -> 404)."""


class IllegalLabTransition(Exception):
    """The case isn't in the state this transition starts from (router -> 409).

    Receiving a case that's already received or cancelled, or cancelling a
    terminal one.
    """


def clinic_today(db: Session) -> date:
    """Today's date in the CLINIC's timezone (not the server's)."""
    settings = db.get(ClinicSettings, 1)
    tz_name = settings.timezone if settings is not None else "UTC"
    return datetime.now(ZoneInfo(tz_name)).date()


def create_lab_case(
    db: Session,
    *,
    patient_id: UUID,
    lab_id: UUID,
    sample_type: str,
    sent_date: date,
    expected_date: date | None = None,
    visit_id: UUID | None = None,
    appointment_id: UUID | None = None,
    tooth_ref: str | None = None,
    notes: str | None = None,
    created_by: UUID | None = None,
) -> LabCase:
    """Record a sample sent to a lab.

    Every referenced row is validated BEFORE anything is written, so a bad id is a
    clean 404 rather than a half-written case and a 500 from the FK (the 4.3
    discipline). The readable `number` comes from the DB sequence on flush.
    """
    if db.get(Patient, patient_id) is None:
        raise PatientNotFound()
    lab = db.get(Lab, lab_id)
    if lab is None:
        raise LabNotFound()
    if visit_id is not None and db.get(Visit, visit_id) is None:
        raise VisitNotFound()
    if appointment_id is not None and db.get(Appointment, appointment_id) is None:
        raise AppointmentNotFound()

    case = LabCase(
        patient_id=patient_id,
        lab_id=lab_id,
        sample_type=sample_type,
        sent_date=sent_date,
        expected_date=expected_date,
        visit_id=visit_id,
        appointment_id=appointment_id,
        tooth_ref=tooth_ref,
        notes=notes,
        created_by=created_by,
        status="sent",
    )
    db.add(case)
    db.flush()  # assigns `number` from the sequence
    return case


def mark_received(db: Session, case: LabCase, received_date: date | None = None) -> None:
    """`sent` -> `received`. Sets the received date (defaults to the clinic's today).

    Only a case that's still at the lab can come back — receiving twice, or
    receiving a cancelled case, raises (router -> 409).
    """
    if case.status != "sent":
        raise IllegalLabTransition()
    case.status = "received"
    case.received_date = received_date or clinic_today(db)
    # A freshly-returned case needs the patient called in, so the nudge is live.
    case.follow_up_done = False


def cancel_case(db: Session, case: LabCase) -> None:
    """Cancel a case (scrapped / sent in error). Only from `sent`."""
    if case.status != "sent":
        raise IllegalLabTransition()
    case.status = "cancelled"


def set_follow_up_done(case: LabCase, done: bool = True) -> None:
    """Tick off the 'call the patient in' nudge (or re-open it).

    A flag, not a status: the receptionist dismisses a reminder, she doesn't have to
    reason about another state. Only meaningful once the case is `received`.
    """
    case.follow_up_done = done


def _rows_with_names(db: Session, stmt) -> list[tuple]:
    """Run a lab-case select joined to patient/lab/appointment for display names."""
    return db.execute(
        stmt.add_columns(Patient.name, Lab.name, Appointment.number)
        .join(Patient, LabCase.patient_id == Patient.id)
        .join(Lab, LabCase.lab_id == Lab.id)
        .outerjoin(Appointment, LabCase.appointment_id == Appointment.id)
    ).all()


def lab_dashboard(db: Session, *, due_within_days: int = 7) -> dict[str, list[tuple]]:
    """The three lists the dashboard shows, each as (case, patient, lab, appt_number).

    - **overdue** — still at the lab and `expected_date` has passed. The case nobody
      chased; surfaced first and loudest.
    - **due_soon** — still at the lab, due from today through `due_within_days`.
      (Cases with no expected date are excluded: nothing to be late against.)
    - **back_from_lab** — received but `follow_up_done` is false, i.e. the patient
      still needs calling in to have it fitted. This list is what stops a returned
      crown sitting in a drawer, given the deliberately simple two-state lifecycle.
    """
    today = clinic_today(db)
    horizon = today + timedelta(days=due_within_days)

    overdue = _rows_with_names(
        db,
        select(LabCase)
        .where(LabCase.status == "sent")
        .where(LabCase.expected_date.is_not(None))
        .where(LabCase.expected_date < today)
        .order_by(LabCase.expected_date),
    )
    due_soon = _rows_with_names(
        db,
        select(LabCase)
        .where(LabCase.status == "sent")
        .where(LabCase.expected_date.is_not(None))
        .where(LabCase.expected_date >= today)
        .where(LabCase.expected_date <= horizon)
        .order_by(LabCase.expected_date),
    )
    back = _rows_with_names(
        db,
        select(LabCase)
        .where(LabCase.status == "received")
        .where(LabCase.follow_up_done.is_(False))
        .order_by(LabCase.received_date.desc().nullslast()),
    )
    return {"overdue": overdue, "due_soon": due_soon, "back_from_lab": back}
