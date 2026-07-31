"""Seed a realistic demo clinic by SIMULATING the workflow forward (6.9).

    docker compose run --rm backend python -m app.seed_demo           # seed
    docker compose run --rm backend python -m app.seed_demo --reset   # wipe first

**Why a simulation rather than table-by-table inserts.** The previous seed filled
each table independently, and the end-to-end walkthrough found exactly the
inconsistencies that invites: appointments marked `done` with no visit, visits
whose appointment was still `arrived`, and 31 patients with no history at all.
Data assembled that way can contradict itself in ways real usage never would.

Here every patient is walked through the same journey the software enforces —
register -> book -> arrive -> treat -> bill -> pay (-> follow up / send to lab) —
in chronological order. If a state is reachable in this file, staff can reach it
in the app, and vice versa. That makes the demo data a rough end-to-end test of
the domain rules as well as something to look at.

Deterministic (fixed RNG seed), so re-seeding reproduces the same clinic.
Idempotent via the audit-log marker; `--reset` clears prior demo data first.

Fake data only — never real patient data on a dev machine (Phase 7+).

Dentists here are `staff_user` rows for assignment and attribution, NOT logins:
the clinic runs on one shared receptionist login (the 6.5 decision).
"""

import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.lab import Lab
from app.models.lab_case import LabCase
from app.models.patient import Patient
from app.models.patient_file import PatientFile
from app.models.payment import Payment
from app.models.procedure_performed import ProcedurePerformed
from app.models.staff_user import StaffUser
from app.models.tooth_condition import ToothCondition
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit
from app.services.audit import record_audit

_DEMO_MARKER = "demo_v2"

# --- the clinic's price list -------------------------------------------------

CATALOGUE = [
    ("Consultation", "300.00"),
    ("Scaling / cleaning", "1500.00"),
    ("Composite filling", "1200.00"),
    ("Root canal treatment", "6000.00"),
    ("Crown (PFM)", "4500.00"),
    ("Crown (Zirconia)", "8000.00"),
    ("Extraction", "1000.00"),
    ("Surgical extraction", "2500.00"),
    ("X-ray (IOPA)", "300.00"),
    ("Denture (complete, per arch)", "12000.00"),
    ("Teeth whitening", "7000.00"),
    ("Fluoride application", "800.00"),
]

MEDICINES = [
    ("Amoxicillin 500mg", "45.00"),
    ("Metronidazole 400mg", "35.00"),
    ("Ibuprofen 400mg", "25.00"),
    ("Paracetamol 650mg", "20.00"),
    ("Chlorhexidine mouthwash", "150.00"),
    ("Lignocaine gel", "90.00"),
]

# (name, email, consultation_fee)
DENTISTS = [
    ("Dr. Meera Prabhu", "meera.demo@clinic.local", "500.00"),
    ("Dr. Anil Kamath", "anil.demo@clinic.local", "300.00"),
]

LABS = [
    ("Sri Dental Lab", "98800 11223", "Davangere"),
    ("Precision Ceramics", "98800 44556", "Bengaluru"),
]

# --- patients: real-looking Karnataka names ----------------------------------

FIRST_NAMES = [
    "Sunita", "Ravi", "Lakshmi", "Manjunath", "Prakash", "Shobha", "Girish",
    "Vidya", "Basavaraj", "Kavya", "Nagaraj", "Rekha", "Suresh", "Anitha",
    "Mahesh", "Jyothi", "Shivakumar", "Deepa", "Ramesh", "Pushpa", "Vinay",
    "Sharada", "Chandrashekar", "Bhavya", "Gopal", "Meena", "Santosh",
    "Roopa", "Kiran", "Savitha", "Umesh", "Nandini", "Harish", "Geetha",
    "Praveen", "Sushma", "Vasanth", "Latha",
]
SURNAMES = [
    "Hegde", "Patil", "Gowda", "Shetty", "Rao", "Kulkarni", "Naik", "Desai",
    "Bhat", "Reddy", "Murthy", "Jain", "Kamath", "Pai", "Nayak", "Joshi",
]

COMPLAINTS = [
    "Pain in lower left back tooth",
    "Sensitivity to cold",
    "Bleeding gums while brushing",
    "Food getting stuck between teeth",
    "Broken filling",
    "Swelling near the gum",
    "Routine check-up",
    "Discoloured front tooth",
    "Difficulty chewing",
    "Wisdom tooth pain",
]

ADDRESSES = [
    "MCC B Block, Davangere",
    "Vidyanagar, Davangere",
    "PJ Extension, Davangere",
    "Shivaji Nagar, Davangere",
    "Nittuvalli, Davangere",
    "Saraswathi Nagar, Davangere",
    "Ashoka Road, Davangere",
    "Jayadeva Circle, Harihar",
]

MEDICAL_NOTES = [
    "Type 2 diabetic — on metformin.",
    "On blood thinners (aspirin). Confirm before extraction.",
    "Allergic to penicillin.",
    "Hypertensive, on medication.",
    "Pregnant — 2nd trimester. Avoid X-rays.",
    "Asthmatic; carries an inhaler.",
]

NOTES_BY_PROCEDURE = {
    "Root canal treatment": [
        "Access opening done. Working length measured. Temporary filling placed.",
        "Cleaning and shaping completed. Calcium hydroxide dressing given.",
        "Obturation done. Patient advised for crown.",
    ],
    "Scaling / cleaning": ["Full-mouth scaling and polishing done. Oral hygiene instructions given."],
    "Composite filling": ["Caries excavated, composite restoration placed and polished."],
    "Extraction": ["Tooth extracted under local anaesthesia. Haemostasis achieved. Post-op instructions given."],
    "Crown (PFM)": ["Tooth prepared, impression taken, temporary crown cemented."],
    "Crown (Zirconia)": ["Tooth prepared, digital impression taken. Shade matched."],
    "Consultation": ["Examination done. Treatment options discussed with the patient."],
}

TEETH = ["11", "16", "21", "26", "31", "36", "37", "41", "46", "47"]

# What each procedure is typically done FOR — so the seeded diagnosis and the
# treatment agree with each other, as they would on a real card.
DIAGNOSES = {
    "Root canal treatment": "Chronic irreversible pulpitis {tooth}",
    "Composite filling": "Dental caries {tooth}",
    "Extraction": "Grossly decayed {tooth} — non-restorable",
    "Surgical extraction": "Impacted third molar {tooth}",
    "Scaling / cleaning": "Chronic generalised gingivitis",
    "Crown (PFM)": "Post-endodontic restoration {tooth}",
    "Crown (Zirconia)": "Post-endodontic restoration {tooth}",
    "Consultation": "Routine examination",
    "Teeth whitening": "Extrinsic staining",
    "Fluoride application": "High caries risk — preventive",
    "Denture (complete, per arch)": "Complete edentulism",
}

_PNG = b"\x89PNG\r\n\x1a\n" + b"demo-xray-bytes" * 8


def _already_seeded(db) -> bool:
    return bool(
        db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == _DEMO_MARKER)
        )
    )


def reset(db) -> None:
    """Delete all clinical/demo data, child tables first.

    Deliberately does NOT touch `staff_user` (the admin row is a real Supabase
    login) or `clinic_settings` (a singleton pinned by a CHECK).
    """
    for model in (
        Payment, InvoiceLine, Invoice, LabCase, PatientFile, ToothCondition,
        ProcedurePerformed, Visit, Appointment, Treatment, Patient,
    ):
        db.execute(delete(model))
    db.execute(delete(Lab))
    db.execute(delete(TreatmentItem))
    db.execute(delete(AuditLog))
    # Drop the name-only demo dentists; keep any real login rows.
    for _, email, _fee in DENTISTS:
        who = db.scalar(select(StaffUser).where(StaffUser.email == email))
        if who is not None:
            db.delete(who)
    db.commit()
    print("reset: cleared previous demo data")


class Clinic:
    """A tiny harness that performs the clinic's actions in chronological order.

    Each method is one thing a human does in the app, and applies the same rules
    the API would — e.g. `treat()` closes the appointment, exactly as
    `services.visits.close_appointment_for_visit` does for a real request.
    """

    def __init__(self, db, rng, dentists, items, meds, labs, actor):
        self.db = db
        self.rng = rng
        self.dentists = dentists
        self.items = {i.name: i for i in items}
        self.meds = meds
        self.labs = labs
        self.actor = actor

    # -- front desk ----------------------------------------------------------

    def register(self, name, *, phone, dob=None, gender=None, notes=None,
                 archived=False, guardian=None, address=None, recall_due=None):
        p = Patient(
            name=name, phone=phone, date_of_birth=dob, gender=gender,
            medical_notes=notes, archived=archived,
            guardian_name=guardian, address=address, recall_due=recall_due,
        )
        self.db.add(p)
        self.db.flush()
        return p

    def book(self, patient, when, *, dentist=None, reason=None, treatment=None,
             duration=30, status="booked", consulting=None):
        """Book a slot, nudging later if that dentist is already busy.

        The DB enforces no-overlap per dentist with a GiST EXCLUDE constraint
        (3.2) — the real guarantee that survives two racing PCs. The seed is
        subject to it like any other client, so rather than hand-pick every
        time (brittle, and it silently breaks the moment the data changes) this
        walks forward in slot-sized steps until it finds a free one. That is
        also what a receptionist does.
        """
        who = dentist or self.dentists[0]
        start = when
        for _ in range(40):  # ~a full working day of slots
            taken = self.db.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(
                    Appointment.dentist_id == who.id,
                    Appointment.status != "cancelled",
                    Appointment.start_time < start + timedelta(minutes=duration),
                    Appointment.start_time
                    + func.make_interval(0, 0, 0, 0, 0, Appointment.duration_min)
                    > start,
                )
            )
            if not taken:
                break
            start += timedelta(minutes=duration)

        appt = Appointment(
            patient_id=patient.id,
            dentist_id=who.id,
            consulting_dentist_id=consulting.id if consulting else None,
            treatment_id=treatment.id if treatment else None,
            start_time=start,
            duration_min=duration,
            status=status,
            reason=reason,
        )
        self.db.add(appt)
        self.db.flush()
        return appt

    # -- the surgery ---------------------------------------------------------

    def _clinical(self, procedure: str, tooth: str | None) -> dict:
        """A plausible OPD card for this procedure (6.10).

        Uses the clinic's own shorthand — "NAD" (no abnormality detected),
        "NRMH" (no relevant medical history) — because that is what the paper
        cards actually say, and demo data that reads like the real thing is what
        makes a demo useful.
        """
        rng = self.rng
        dx = DIAGNOSES.get(procedure)

        card: dict = {
            "history_note": rng.choice(["NRMH", "NRMH", "NRMH", "Diabetic — on metformin",
                                        "Hypertensive, on medication"]),
            "habits": rng.choice(["Nil", "Nil", "Tobacco chewing", "Smoking — 5/day"]),
            "extra_oral": "NAD",
            "intra_oral": rng.choice(["NAD", "Generalised stains", "Calculus present"]),
            "soft_tissues": "NAD",
            "occlusion": rng.choice(["Class I molar relation", "NAD", "Class II div 1"]),
            "missing_teeth": rng.choice(["Nil", "Nil", "38, 48"]),
        }

        # BP on roughly half of visits, and reliably before anything surgical.
        if "xtraction" in procedure or rng.random() < 0.5:
            systolic = rng.choice([112, 118, 122, 126, 130, 138, 146])
            card["bp_systolic"] = systolic
            card["bp_diastolic"] = systolic - rng.choice([38, 42, 46])

        if tooth:
            card["hard_tissue"] = f"{rng.choice(['Proximal', 'Occlusal', 'Cervical'])} caries {tooth}"

        if dx:
            card["provisional_diagnosis"] = dx.format(tooth=tooth or "")
            card["final_diagnosis"] = dx.format(tooth=tooth or "")
            # X-rays for the work that clinically warrants one.
            if procedure in ("Root canal treatment", "Extraction", "Surgical extraction"):
                card["investigations"] = ["iopa"]
                card["investigation_notes"] = f"IOPA wrt {tooth}" if tooth else "IOPA"

        return card

    def treat(self, patient, *, when, procedures, appointment=None, treatment=None,
              title=None, tooth=None, complete=True, dentist=None, consulting=None,
              complaint=None, notes=None, phase=None, clinical=True):
        """Record a sitting. Creates/closes the treatment and CLOSES the
        appointment, mirroring the 6.8 rule so the demo data can never contain
        the "treated but still marked arrived" state the walkthrough found."""
        if treatment is None:
            treatment = Treatment(
                patient_id=patient.id,
                title=title or procedures[0],
                tooth_ref=tooth,
                status="in_progress",
                started_at=when,
            )
            self.db.add(treatment)
            self.db.flush()

        if phase is not None:
            treatment.phase = phase

        who = dentist or self.dentists[0]
        first = procedures[0]
        visit = Visit(
            patient_id=patient.id,
            treatment_id=treatment.id,
            appointment_id=appointment.id if appointment else None,
            dentist_id=who.id,
            consulting_dentist_id=consulting.id if consulting else None,
            visit_date=when,
            complaint=complaint or self.rng.choice(COMPLAINTS),
            clinical_notes=notes or self.rng.choice(
                NOTES_BY_PROCEDURE.get(first, ["Treatment carried out as planned."])
            ),
            # The OPD card (6.10). Filled on most visits but deliberately NOT
            # all — a real day has quick sittings where only the complaint and
            # what was done get written down, and the screens must look right
            # for those too.
            **(self._clinical(first, tooth) if clinical else {}),
        )
        self.db.add(visit)
        self.db.flush()

        for name in procedures:
            item = self.items.get(name)
            if item is not None:
                self.db.add(
                    ProcedurePerformed(
                        visit_id=visit.id,
                        treatment_item_id=item.id,
                        tooth_ref=tooth if name != "Consultation" else None,
                    )
                )

        # Medicines ride the same pipeline (6.7) — dispensed about a third of
        # the time, as in a real surgery.
        if self.rng.random() < 0.35:
            med = self.rng.choice(self.meds)
            self.db.add(
                ProcedurePerformed(visit_id=visit.id, treatment_item_id=med.id, tooth_ref=None)
            )

        if complete:
            treatment.status = "completed"
            treatment.closed_at = when

        # The 6.8 rule: recording the sitting finishes the appointment.
        if appointment is not None and appointment.status in ("booked", "arrived"):
            appointment.status = "done"

        self.db.flush()
        return visit, treatment

    # -- billing -------------------------------------------------------------

    def bill(self, visit, *, discount="0.00", consultation_for=None):
        """Generate the invoice, freezing each line's price (the 5.2 rule)."""
        rows = self.db.execute(
            select(TreatmentItem.id, TreatmentItem.name, TreatmentItem.default_price)
            .join(ProcedurePerformed, ProcedurePerformed.treatment_item_id == TreatmentItem.id)
            .where(ProcedurePerformed.visit_id == visit.id)
            .order_by(TreatmentItem.name)
        ).all()

        lines = [
            InvoiceLine(treatment_item_id=iid, description=name, amount=price)
            for iid, name, price in rows
        ]
        # A per-dentist consultation fee bills as a CUSTOM line (6.7) — it has
        # no catalogue row.
        if consultation_for is not None and consultation_for.consultation_fee is not None:
            lines.append(
                InvoiceLine(
                    treatment_item_id=None,
                    description=f"Consultation — {consultation_for.name}",
                    amount=consultation_for.consultation_fee,
                )
            )
        if not lines:
            return None

        subtotal = sum((ln.amount for ln in lines), Decimal("0"))
        disc = Decimal(discount)
        invoice = Invoice(
            patient_id=visit.patient_id,
            visit_id=visit.id,
            subtotal=subtotal,
            discount=disc,
            total=subtotal - disc,
            status="unpaid",
            created_at=visit.visit_date,
        )
        self.db.add(invoice)
        self.db.flush()
        for ln in lines:
            ln.invoice_id = invoice.id
            self.db.add(ln)
        self.db.flush()
        return invoice

    def pay(self, invoice, *, amount=None, mode=None, when=None):
        """Take a payment and DERIVE the status from the sum (the 5.3 rule)."""
        amt = Decimal(amount) if amount is not None else invoice.total
        self.db.add(
            Payment(
                invoice_id=invoice.id,
                amount=amt,
                mode=mode or self.rng.choice(["cash", "upi", "card"]),
                paid_at=when or invoice.created_at,
            )
        )
        self.db.flush()

        paid = self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.invoice_id == invoice.id
            )
        ) or Decimal("0")
        if paid <= 0:
            invoice.status = "unpaid"
        elif paid < invoice.total:
            invoice.status = "partially_paid"
        else:
            invoice.status = "paid"
        self.db.flush()

    # -- lab -----------------------------------------------------------------

    def send_to_lab(self, patient, visit, *, sent, expected, sample, tooth,
                    status="sent", received=None, follow_up_done=False):
        case = LabCase(
            patient_id=patient.id,
            lab_id=self.rng.choice(self.labs).id,
            visit_id=visit.id if visit else None,
            sample_type=sample,
            tooth_ref=tooth,
            sent_date=sent,
            expected_date=expected,
            received_date=received,
            status=status,
            follow_up_done=follow_up_done,
            created_by=self.actor.id,
        )
        self.db.add(case)
        self.db.flush()
        return case

    def chart(self, patient, marks, visit=None):
        """Mark teeth on the patient's chart (6.11).

        `marks` is a list of (tooth, condition) pairs. Seeded directly rather
        than through the supersede path — this is the patient's chart as it
        stands today, not a history of corrections.
        """
        for tooth, condition in marks:
            self.db.add(
                ToothCondition(
                    patient_id=patient.id,
                    tooth=tooth,
                    condition=condition,
                    surfaces="MOD" if condition in ("caries", "filled") else None,
                    recorded_visit_id=visit.id if visit else None,
                    recorded_by=self.actor.id,
                )
            )
        self.db.flush()

    def attach_xray(self, patient, visit, caption):
        self.db.add(
            PatientFile(
                patient_id=patient.id,
                visit_id=visit.id if visit else None,
                uploaded_by=self.actor.id,
                kind="image",
                original_filename=f"iopa-{self.rng.randint(1000, 9999)}.png",
                content_type="image/png",
                size_bytes=len(_PNG),
                caption=caption,
                storage_key=f"demo/{uuid4()}.png",
            )
        )


def main(do_reset: bool = False) -> None:
    rng = random.Random(20260730)

    with SessionLocal() as db:
        if do_reset:
            reset(db)
        elif _already_seeded(db):
            print("seed_demo: already seeded (marker present), skipping. Use --reset to redo.")
            return

        actor = db.scalar(select(StaffUser).where(StaffUser.roles.any("admin")))
        if actor is None:
            print("No admin staff row found — run `python -m app.seed` first.")
            return

        # --- the catalogue ---
        items = []
        for name, price in CATALOGUE:
            it = TreatmentItem(name=name, default_price=Decimal(price), kind="treatment")
            db.add(it)
            items.append(it)
        meds = []
        for name, price in MEDICINES:
            m = TreatmentItem(name=name, default_price=Decimal(price), kind="medicine")
            db.add(m)
            meds.append(m)

        # --- dentists ---
        dentists = []
        for name, email, fee in DENTISTS:
            d = db.scalar(select(StaffUser).where(StaffUser.email == email))
            if d is None:
                d = StaffUser(
                    id=uuid4(), name=name, email=email, roles=["dentist"],
                    active=True, consultation_fee=Decimal(fee),
                )
                db.add(d)
            dentists.append(d)

        labs = [Lab(name=n, phone=p, address=a) for n, p, a in LABS]
        db.add_all(labs)
        db.flush()

        c = Clinic(db, rng, dentists, items, meds, labs, actor)

        # Clinic-day helper: appointments land in working hours.
        def at(days_ago: int, hour: int, minute: int = 0) -> datetime:
            d = datetime.now(timezone.utc).date() - timedelta(days=days_ago)
            return datetime.combine(d, time(hour, minute), tzinfo=timezone.utc)

        today = datetime.now(timezone.utc).date()
        used_names: set[str] = set()

        def person(i: int) -> str:
            while True:
                n = f"{FIRST_NAMES[i % len(FIRST_NAMES)]} {rng.choice(SURNAMES)}"
                if n not in used_names:
                    used_names.add(n)
                    return n

        def phone() -> str:
            return f"9{rng.randint(700000000, 899999999)}"

        def dob(age: int) -> date:
            return date(today.year - age, rng.randint(1, 12), rng.randint(1, 28))

        made = {"patients": 0, "appointments": 0, "visits": 0,
                "invoices": 0, "payments": 0, "lab": 0, "files": 0}
        idx = 0

        # ============================================================ GROUP A
        # 12 completed single-visit journeys, fully billed and paid.
        single = ["Scaling / cleaning", "Composite filling", "Extraction",
                  "Teeth whitening", "Fluoride application", "Consultation"]
        for k in range(12):
            days = 100 - k * 7
            age = rng.randint(19, 68)
            p = c.register(
                person(idx), phone=phone(), dob=dob(age),
                gender=rng.choice(["female", "male"]),
                notes=rng.choice(MEDICAL_NOTES) if rng.random() < 0.2 else None,
                address=rng.choice(ADDRESSES),
                # Completed work earns a recall — Phase 4. Spread across the
                # next few months, and a couple already overdue so the
                # dashboard's "due for a check-up" card has content.
                recall_due=today + timedelta(days=rng.choice([-20, -5, 14, 60, 120, 150])),
            )
            idx += 1
            proc = single[k % len(single)]
            when = at(days, rng.choice([10, 11, 12, 16, 17]), rng.choice([0, 30]))
            dentist = dentists[k % 2]
            appt = c.book(p, when, dentist=dentist, reason=proc, status="arrived")
            visit, _ = c.treat(
                p, when=when, procedures=[proc], appointment=appt,
                title=proc, tooth=rng.choice(TEETH) if proc != "Consultation" else None,
                complete=True, dentist=dentist,
                # Finished single-visit work sits in Phase 4 (maintenance).
                phase=4,
                # A few quick sittings get only the basics written up, as in life.
                clinical=k % 5 != 0,
            )
            # Most adults have some restorative history — a chart that is
            # entirely blank on every patient would tell us nothing about
            # whether the screen works.
            if k % 3 != 2:
                c.chart(
                    p,
                    [
                        (rng.choice(["16", "26", "36", "46"]), "filled"),
                        (rng.choice(["17", "27", "37", "47"]), "caries"),
                        *([("38", "impacted")] if k % 4 == 0 else []),
                        *([(rng.choice(["18", "28"]), "missing")] if k % 5 == 0 else []),
                    ],
                    visit=visit,
                )
            inv = c.bill(visit, consultation_for=dentist if k % 4 == 0 else None)
            if inv:
                c.pay(inv, when=when)
                made["invoices"] += 1
                made["payments"] += 1
            made["patients"] += 1
            made["appointments"] += 1
            made["visits"] += 1

        # ============================================================ GROUP B
        # 8 multi-sitting treatments still in progress, follow-up BOOKED.
        for k in range(8):
            p = c.register(
                person(idx), phone=phone(), dob=dob(rng.randint(24, 62)),
                gender=rng.choice(["female", "male"]),
                notes=rng.choice(MEDICAL_NOTES) if rng.random() < 0.25 else None,
            )
            idx += 1
            tooth = rng.choice(TEETH)
            dentist = dentists[k % 2]
            big = "Root canal treatment" if k % 2 == 0 else "Crown (PFM)"
            title = f"{'RCT' if k % 2 == 0 else 'Crown'} tooth {tooth}"

            # Sitting 1
            d1 = 40 - k * 4
            w1 = at(d1, rng.choice([10, 11, 15]), rng.choice([0, 30]))
            a1 = c.book(p, w1, dentist=dentist, reason=title, status="arrived")
            v1, treatment = c.treat(
                p, when=w1, procedures=[big, "X-ray (IOPA)"], appointment=a1,
                title=title, tooth=tooth, complete=False, dentist=dentist,
                # Sitting 1 of a multi-visit case is disease control (Phase 2).
                phase=2,
            )
            inv1 = c.bill(v1, consultation_for=dentist)
            if inv1:
                # Part-paid: a real multi-sitting case often pays in instalments.
                c.pay(inv1, amount=str((inv1.total / 2).quantize(Decimal("0.01"))), when=w1)
                made["invoices"] += 1
                made["payments"] += 1

            # Sitting 2, under the SAME treatment
            d2 = d1 - 10
            w2 = at(d2, rng.choice([10, 12, 16]), rng.choice([0, 30]))
            a2 = c.book(p, w2, dentist=dentist, reason=f"{title} — sitting 2",
                        treatment=treatment, status="arrived")
            v2, _ = c.treat(
                p, when=w2, procedures=[big], appointment=a2, treatment=treatment,
                tooth=tooth, complete=False, dentist=dentist,
                consulting=dentists[(k + 1) % 2] if k % 3 == 0 else None,
                # By sitting 2 the case has moved to definitive treatment.
                phase=3,
            )
            inv2 = c.bill(v2)
            if inv2:
                made["invoices"] += 1
                if k % 3 != 0:  # some left unpaid on purpose
                    c.pay(inv2, when=w2)
                    made["payments"] += 1

            # The next sitting IS booked — so these must NOT appear on the
            # follow-up report.
            c.book(p, at(-(3 + k), rng.choice([10, 11, 15]), 0), dentist=dentist,
                   reason=f"{title} — next sitting", treatment=treatment, status="booked")

            # The tooth under treatment is charted as what it now IS, so the
            # chart agrees with the clinical record rather than contradicting it.
            c.chart(
                p,
                [
                    (tooth, "root_canal" if big == "Root canal treatment" else "crown"),
                    (rng.choice(["15", "25", "35", "45"]), "filled"),
                ],
                visit=v1,
            )

            if k < 3:
                c.attach_xray(p, v1, f"IOPA tooth {tooth} — pre-op")
                made["files"] += 1

            made["patients"] += 1
            made["appointments"] += 3
            made["visits"] += 2

        # ============================================================ GROUP C
        # 4 open treatments with NO future appointment -> the 4.8 report.
        for k in range(4):
            p = c.register(person(idx), phone=phone(), dob=dob(rng.randint(28, 70)),
                           gender=rng.choice(["female", "male"]))
            idx += 1
            tooth = rng.choice(TEETH)
            dentist = dentists[k % 2]
            when = at(25 - k * 5, rng.choice([11, 14, 17]), 30)
            appt = c.book(p, when, dentist=dentist, reason=f"RCT tooth {tooth}", status="arrived")
            visit, _ = c.treat(
                p, when=when, procedures=["Root canal treatment"], appointment=appt,
                title=f"RCT tooth {tooth}", tooth=tooth, complete=False, dentist=dentist,
            )
            inv = c.bill(visit)
            if inv:
                made["invoices"] += 1
                if k % 2 == 0:
                    c.pay(inv, amount="1000.00", when=when)
                    made["payments"] += 1
            made["patients"] += 1
            made["appointments"] += 1
            made["visits"] += 1

        # ============================================================ GROUP D
        # 3 treated-but-UNBILLED visits -> the new "Ready to bill" card.
        for k in range(3):
            p = c.register(person(idx), phone=phone(), dob=dob(rng.randint(20, 55)),
                           gender=rng.choice(["female", "male"]))
            idx += 1
            proc = ["Scaling / cleaning", "Composite filling", "Extraction"][k]
            when = at(k, rng.choice([10, 12, 16]), 0)
            appt = c.book(p, when, dentist=dentists[k % 2], reason=proc, status="arrived")
            c.treat(p, when=when, procedures=[proc], appointment=appt, title=proc,
                    tooth=rng.choice(TEETH), complete=True, dentist=dentists[k % 2])
            made["patients"] += 1
            made["appointments"] += 1
            made["visits"] += 1

        # ============================================================ GROUP E
        # 5 lab cases across every stage.
        lab_plan = [
            ("crown", 14, -5, "sent", None, False),        # overdue
            ("bridge", 9, -2, "sent", None, False),        # overdue
            ("denture_partial", 4, 3, "sent", None, False),  # due soon
            ("crown", 20, -12, "received", 6, False),      # back, needs a call
            ("veneer", 26, -18, "received", 15, True),     # back, dealt with
        ]
        for k, (sample, sent_ago, expected_offset, status, recv_ago, done) in enumerate(lab_plan):
            p = c.register(person(idx), phone=phone(), dob=dob(rng.randint(30, 66)),
                           gender=rng.choice(["female", "male"]))
            idx += 1
            tooth = rng.choice(TEETH)
            dentist = dentists[k % 2]
            when = at(sent_ago, rng.choice([10, 11, 15]), 0)
            appt = c.book(p, when, dentist=dentist, reason=f"Crown prep tooth {tooth}",
                          status="arrived")
            visit, treatment = c.treat(
                p, when=when, procedures=["Crown (PFM)"], appointment=appt,
                title=f"Crown tooth {tooth}", tooth=tooth, complete=False, dentist=dentist,
            )
            inv = c.bill(visit)
            if inv:
                c.pay(inv, amount=str((inv.total / 2).quantize(Decimal("0.01"))), when=when)
                made["invoices"] += 1
                made["payments"] += 1
            c.send_to_lab(
                p, visit,
                sent=today - timedelta(days=sent_ago),
                expected=today - timedelta(days=expected_offset)
                if expected_offset > 0 else today + timedelta(days=-expected_offset),
                sample=sample, tooth=tooth, status=status,
                received=today - timedelta(days=recv_ago) if recv_ago else None,
                follow_up_done=done,
            )
            made["patients"] += 1
            made["appointments"] += 1
            made["visits"] += 1
            made["lab"] += 1

        # A cancelled lab case, so that filter has content.
        cancelled_p = c.register(person(idx), phone=phone(), dob=dob(44), gender="male")
        idx += 1
        cw = at(30, 11, 0)
        ca = c.book(cancelled_p, cw, dentist=dentists[0], reason="Crown prep", status="arrived")
        cv, _ = c.treat(cancelled_p, when=cw, procedures=["Crown (PFM)"], appointment=ca,
                        title="Crown tooth 26", tooth="26", complete=False)
        c.send_to_lab(cancelled_p, cv, sent=today - timedelta(days=30),
                      expected=today - timedelta(days=23), sample="crown", tooth="26",
                      status="cancelled")
        made["patients"] += 1
        made["appointments"] += 1
        made["visits"] += 1
        made["lab"] += 1

        # ========================================================= PAEDIATRIC
        # A child in mixed dentition, transcribed from the clinic's own sample
        # OPD card. Exercises the guardian field, deciduous-era occlusion
        # terminology, and a fully filled clinical record on one screen.
        child = c.register(
            person(idx), phone=phone(), dob=dob(9), gender="male",
            guardian=f"S/O {rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}",
            address=rng.choice(ADDRESSES),
            recall_due=today + timedelta(days=90),
        )
        idx += 1
        cw = at(2, 10, 30)
        capp = c.book(child, cw, dentist=dentists[0], reason="Pain upper left back tooth",
                      status="arrived")
        cvisit, ctreatment = c.treat(
            child, when=cw, procedures=["Root canal treatment", "X-ray (IOPA)"],
            appointment=capp, title="RCT tooth 26 (paediatric)", tooth="26",
            complete=False, dentist=dentists[0], phase=2,
            complaint="Pain in upper left back tooth region since 3 days",
            notes="Access opening done. Working length measured. Temporary filling placed.",
            clinical=False,  # set explicitly just below
        )
        cvisit.history_note = "NRMH"
        cvisit.habits = "Nil"
        cvisit.extra_oral = "NAD"
        cvisit.intra_oral = "NAD"
        cvisit.soft_tissues = "NAD"
        cvisit.hard_tissue = "Proximal caries 26"
        cvisit.occlusion = "Mesial step terminal plane"
        cvisit.missing_teeth = "Nil"
        cvisit.investigations = ["iopa"]
        cvisit.investigation_notes = "IOPA wrt 26"
        cvisit.provisional_diagnosis = "Chronic irreversible pulpitis 26"
        cvisit.differential_diagnosis = "Reversible pulpitis"
        cvisit.final_diagnosis = "Chronic irreversible pulpitis 26"
        cvisit.referred_to = "Pedodontics"
        cvisit.referral_note = "For completion of RCT under behaviour guidance"
        # Mixed dentition — permanent AND deciduous teeth in one mouth. This is
        # the case the deciduous half of the chart exists for.
        c.chart(
            child,
            [
                ("26", "root_canal"),
                ("16", "caries"),
                ("55", "filled"),
                ("75", "caries"),
                ("84", "missing"),
            ],
            visit=cvisit,
        )
        db.flush()
        made["patients"] += 1
        made["appointments"] += 1
        made["visits"] += 1

        # ============================================================ GROUP F
        # 2 walk-ins (no appointment at all) — a very common real case.
        for k in range(2):
            p = c.register(person(idx), phone=phone(), dob=dob(rng.randint(21, 60)),
                           gender=rng.choice(["female", "male"]))
            idx += 1
            when = at(k + 1, 18, 0)
            visit, _ = c.treat(
                p, when=when, procedures=["Consultation", "X-ray (IOPA)"],
                appointment=None, title="Emergency consultation",
                complaint="Walk-in — sudden pain", complete=True, dentist=dentists[k % 2],
            )
            inv = c.bill(visit, consultation_for=dentists[k % 2])
            if inv:
                c.pay(inv, when=when)
                made["invoices"] += 1
                made["payments"] += 1
            made["patients"] += 1
            made["visits"] += 1

        # ============================================================ GROUP G
        # No-shows and cancellations, so the calendar + no-show report have data.
        for k in range(3):
            p = c.register(person(idx), phone=phone(), dob=dob(rng.randint(22, 58)),
                           gender=rng.choice(["female", "male"]))
            idx += 1
            c.book(p, at(12 - k * 3, rng.choice([10, 14]), 30), dentist=dentists[k % 2],
                   reason="Check-up", status="no_show" if k < 2 else "cancelled")
            made["patients"] += 1
            made["appointments"] += 1

        # An archived patient, so the archive filter hides something real.
        c.register(person(idx), phone=phone(), dob=dob(71), gender="female",
                   notes="Moved out of town.", archived=True)
        idx += 1
        made["patients"] += 1

        # ============================================================ TODAY
        # A live day: some finished, one in the chair, several still to come —
        # so the dashboard is alive the moment it's opened.
        today_plan = [
            (9, 30, "Scaling / cleaning", "done"),
            (10, 15, "Composite filling", "done"),
            (11, 0, "Root canal treatment", "arrived"),
            (12, 0, "Consultation", "booked"),
            (16, 30, "Extraction", "booked"),
            (17, 15, "Check-up", "booked"),
        ]
        for k, (hh, mm, reason, status) in enumerate(today_plan):
            p = c.register(person(idx), phone=phone(), dob=dob(rng.randint(18, 64)),
                           gender=rng.choice(["female", "male"]),
                           notes=rng.choice(MEDICAL_NOTES) if k == 2 else None)
            idx += 1
            dentist = dentists[k % 2]
            when = at(0, hh, mm)
            appt = c.book(p, when, dentist=dentist, reason=reason, status=status)
            made["patients"] += 1
            made["appointments"] += 1

            if status == "done":
                # Finished today AND written up -> billed, one left to pay.
                visit, _ = c.treat(p, when=when, procedures=[reason], appointment=appt,
                                   title=reason, tooth=rng.choice(TEETH),
                                   complete=True, dentist=dentist)
                inv = c.bill(visit, consultation_for=dentist if k == 0 else None)
                if inv:
                    made["invoices"] += 1
                    if k == 0:
                        c.pay(inv, when=when)
                        made["payments"] += 1
                made["visits"] += 1

        # One appointment finished today with NOTHING recorded -> the new nudge.
        p = c.register(person(idx), phone=phone(), dob=dob(37), gender="male")
        idx += 1
        c.book(p, at(0, 9, 0), dentist=dentists[0], reason="Follow-up check", status="done")
        made["patients"] += 1
        made["appointments"] += 1

        record_audit(db, actor_id=actor.id, action=_DEMO_MARKER, entity="seed",
                     entity_id=None, details=made)
        db.commit()

        print("seeded a demo clinic:")
        for k, v in made.items():
            print(f"  {k:14} {v}")


if __name__ == "__main__":
    main(do_reset="--reset" in sys.argv)
