"""Treatment lifecycle — close / reopen (step 4.5).

The **fourth `services/` module.** A treatment's status is a tiny state machine,
`in_progress <-> completed`, and this holds the two transitions so the router
stays thin and the rule is unit-testable without HTTP.

Until now a treatment's status only changed as a side effect of recording a
visit (4.3, `services/visits._apply_status`). This module lets the dentist:

- **close** a treatment after the fact, without recording a visit ("that course
  is finished"), and
- **reopen** a completed one ("the patient came back"), which is exactly the
  remedy for the 409 the visit form hits when someone records against a closed
  treatment (4.4).

`status` and `closed_at` are changed together — a completed treatment must carry
a close time, an open one must not — mirroring `_apply_status`. Like the other
services this raises a **domain exception**, not `HTTPException`, so the router
owns status codes (the 4.3 standing decision). `datetime.now(timezone.utc)`
because closing is a business event, not a row-write timestamp.
"""

from datetime import datetime, timezone

from app.models.treatment import Treatment


class IllegalTreatmentTransition(Exception):
    """The treatment isn't in the state this transition starts from.

    Closing an already-completed treatment, or reopening one that's still open.
    The router maps this to 409.
    """


def close_treatment(treatment: Treatment) -> None:
    """in_progress -> completed. Sets closed_at."""
    if treatment.status != "in_progress":
        raise IllegalTreatmentTransition()
    treatment.status = "completed"
    treatment.closed_at = datetime.now(timezone.utc)


def reopen_treatment(treatment: Treatment) -> None:
    """completed -> in_progress. Clears closed_at."""
    if treatment.status != "completed":
        raise IllegalTreatmentTransition()
    treatment.status = "in_progress"
    treatment.closed_at = None
