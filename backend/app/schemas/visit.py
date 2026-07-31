"""Visit request/response schemas (step 4.3).

The shape that matters here is on `VisitCreate`: a visit is recorded with EITHER
an existing `treatment_id` (this sitting continues a thread) OR a `treatment`
stub (this is new work — create the thread). Exactly one, enforced by a model
validator so a malformed request is a 422 before it reaches the router.

That either/or is what keeps BUILD_PLAN §3's promise: the receptionist recording
a one-off cleaning sends a stub and never types the word "treatment". The server
creates it — and, when `treatment_status="completed"`, closes it in the same
call, so a single-visit cleaning never lingers as an open thread on the 4.8
dashboard.

`treatment_status` is a `Literal`, so an unknown value is a schema 422 — the same
choice `AppointmentStatusUpdate` makes for appointment status (3.5).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# What can be ordered under "Inv:" on the OPD card (6.10). A Literal, so an
# unknown value is a 422 long before it reaches the column — the same choice
# `treatment_status` and `payment.mode` make.
Investigation = Literal["iopa", "opg_conventional", "opg_digital", "other"]


class ClinicalRecord(BaseModel):
    """The OPD card's clinical fields, shared by create / update / read (6.10).

    Every field is optional: a routine scaling fills almost none of them, and a
    form that demands seven findings for a cleaning is one people stop using.

    Free text rather than code lists — dentistry has no vocabulary small enough
    for these, and the clinic's own shorthand ("NAD", "NRMH") is more useful to
    them than an enum we invented.
    """

    # History as at THIS sitting, distinct from patient.medical_notes (standing).
    history_note: str | None = None

    # Vitals. BP matters chairside — before an extraction or local anaesthetic.
    bp_systolic: int | None = Field(default=None, ge=50, le=300)
    bp_diastolic: int | None = Field(default=None, ge=30, le=200)

    # Examination, in the card's order.
    habits: str | None = None
    extra_oral: str | None = None
    intra_oral: str | None = None
    soft_tissues: str | None = None
    hard_tissue: str | None = None
    occlusion: str | None = None
    missing_teeth: str | None = None
    other_findings: str | None = None

    investigations: list[Investigation] = Field(default_factory=list)
    investigation_notes: str | None = None

    # The clinical conclusion — the gap 6.10 exists to close.
    provisional_diagnosis: str | None = None
    differential_diagnosis: str | None = None
    final_diagnosis: str | None = None

    referred_to: str | None = None
    referral_note: str | None = None


class TreatmentStub(BaseModel):
    """The 'start a new thread' block: what work is this, on which tooth."""

    title: str = Field(
        min_length=1, description="What is being done, e.g. 'RCT tooth 36'."
    )
    tooth_ref: str | None = Field(
        default=None, description="FDI tooth number, e.g. '36'. Omit if not tooth-specific."
    )


class ProcedureIn(BaseModel):
    """One catalogue procedure performed during the visit."""

    treatment_item_id: UUID = Field(description="A treatment_item from the 4.1 catalogue.")
    tooth_ref: str | None = Field(
        default=None,
        description="Per-procedure tooth, which may differ from the treatment's.",
    )


class VisitCreate(ClinicalRecord):
    """Body for recording a sitting.

    Supply EITHER `treatment_id` (continue an existing treatment) OR `treatment`
    (start a new one) — never both, never neither.

    Inherits the OPD card's clinical fields from `ClinicalRecord` (6.10).
    """

    patient_id: UUID

    # --- exactly one of these two ---
    treatment_id: UUID | None = Field(
        default=None, description="Continue this existing treatment."
    )
    treatment: TreatmentStub | None = Field(
        default=None, description="Start a new treatment with these details."
    )

    # Optional links. appointment_id is None for a walk-in.
    appointment_id: UUID | None = None
    # The PRIMARY dentist (defaults to whoever records it if omitted, in the router).
    dentist_id: UUID | None = None
    # The CONSULTING (second) dentist for a handoff — always optional (6.3).
    consulting_dentist_id: UUID | None = None

    # Defaults to now() server-side when omitted.
    visit_date: datetime | None = None

    complaint: str | None = None
    clinical_notes: str | None = None

    procedures: list[ProcedureIn] = Field(default_factory=list)

    # The dentist's answer to "is this finished?". `completed` closes the
    # treatment (sets closed_at) in this same request — the auto-close half of
    # the rule. Defaults to in_progress: leaving work open is the safer default,
    # because an open treatment gets flagged for follow-up (4.8) whereas a
    # wrongly-closed one silently disappears.
    treatment_status: Literal["in_progress", "completed"] = "in_progress"

    @model_validator(mode="after")
    def exactly_one_treatment_form(self) -> "VisitCreate":
        """Require exactly one of treatment_id / treatment.

        Neither would leave visit.treatment_id NULL, which the DB forbids (4.2);
        both is ambiguous — we'd have to guess whether to create or continue.
        """
        has_id = self.treatment_id is not None
        has_stub = self.treatment is not None
        if has_id == has_stub:
            raise ValueError(
                "Provide exactly one of 'treatment_id' (continue an existing "
                "treatment) or 'treatment' (start a new one)."
            )
        return self


class VisitUpdate(ClinicalRecord):
    """Body for editing a recorded visit (PATCH). Every field optional.

    Deliberately cannot move a visit to a different treatment or patient: that's
    a data-repair operation, not a clinical edit, and silently re-threading a
    sitting would corrupt the treatment history. Procedures are not edited here
    either — 4.4's screen re-records them if needed.

    The clinical fields are inherited and editable: a diagnosis genuinely does
    get revised once an X-ray comes back, which is the whole point of having
    both a provisional and a final one.
    """

    complaint: str | None = None
    clinical_notes: str | None = None
    visit_date: datetime | None = None
    # Inherited `investigations` defaults to [] on the base; on a PATCH that
    # would wipe the list whenever the caller omits it, so it is re-declared as
    # None-by-default and the router only applies fields that were actually sent
    # (`exclude_unset`).
    investigations: list[Investigation] | None = None


class ProcedureRead(BaseModel):
    """A performed procedure, with its catalogue name resolved.

    The name is joined in by the router so a client rendering a visit doesn't
    have to fetch the whole catalogue to label two rows.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    treatment_item_id: UUID
    treatment_item_name: str
    tooth_ref: str | None


class TreatmentSummary(BaseModel):
    """The thread a visit belongs to, enough to show context on the visit."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    tooth_ref: str | None
    status: str
    phase: int | None = None
    started_at: datetime
    closed_at: datetime | None


class VisitRead(ClinicalRecord):
    """Everything the API returns about one visit.

    Includes the treatment summary and the procedures: a sitting read on its own,
    without the thread it belongs to or what was done, isn't a useful clinical
    record. One GET returns all three — plus, from 6.10, the OPD card's clinical
    fields, which the print view renders.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # Human-readable OPD number, shown as "V-1042".
    number: int
    patient_id: UUID
    treatment_id: UUID
    appointment_id: UUID | None
    dentist_id: UUID | None
    dentist_name: str | None
    consulting_dentist_id: UUID | None
    consulting_dentist_name: str | None
    visit_date: datetime
    complaint: str | None
    clinical_notes: str | None
    created_at: datetime
    updated_at: datetime

    treatment: TreatmentSummary
    procedures: list[ProcedureRead]


class VisitListResponse(BaseModel):
    """A patient's or treatment's visits plus the total count."""

    items: list[VisitRead]
    total: int


class UnbilledVisit(BaseModel):
    """One row of the "to bill" worklist (6.8).

    A deliberately flat, lean shape — the dashboard card needs a name, what was
    done and when, and a link. Returning full `VisitRead` objects would mean
    shipping clinical notes to a billing list that has no use for them.
    """

    id: UUID
    patient_id: UUID
    patient_name: str
    treatment_title: str
    visit_date: datetime
    dentist_name: str | None = None
    procedure_count: int


class UnbilledVisitsResponse(BaseModel):
    items: list[UnbilledVisit]
    total: int
