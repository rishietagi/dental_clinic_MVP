"""Seed a full, realistic demo dataset for local review (step 6.3).

    docker compose run --rm backend python -m app.seed_demo

Populates EVERY screen with data so the app can be demoed and every feature seen
with real content: a couple of dentists, a treatment catalogue, ~50 patients (via
the existing patient seed), a spread of appointments (past/today/future across all
statuses, some with a consulting dentist), visits with procedures (primary +
consulting dentist), invoices with payments (paid / partially paid / unpaid), and a
few uploaded-file placeholders.

Fake data only — never real patient data on a dev machine (Phase 7+). Idempotent:
guarded on a demo marker in the audit log, so re-running does nothing. To reset,
drop + re-create the DB (or delete the demo rows) and re-run.

Note on dentists: these are `staff_user` rows for assignment/display. A real
Supabase LOGIN for a dentist is a separate concern (Supabase Auth) and out of scope
here — you sign in as the seeded admin; the demo dentists exist to be referenced by
appointments/visits.
"""

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select

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
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit
from app.services.audit import record_audit
from app.seed_patients import generate_patients

_DEMO_MARKER = "demo_v1"

# The catalogue the invoices price from.
CATALOGUE = [
    ("Consultation", "300.00"),
    ("Scaling / cleaning", "1500.00"),
    ("Composite filling", "1200.00"),
    ("Root canal treatment", "6000.00"),
    ("Crown (PFM)", "4500.00"),
    ("Extraction", "1000.00"),
    ("X-ray (IOPA)", "300.00"),
]

# Medicines dispensed at the chair (6.7). Same table as CATALOGUE, kind='medicine'.
MEDICINES = [
    ("Amoxicillin 500mg", "45.00"),
    ("Metronidazole 400mg", "35.00"),
    ("Ibuprofen 400mg", "25.00"),
    ("Paracetamol 650mg", "20.00"),
    ("Chlorhexidine mouthwash", "150.00"),
]

# (name, email, consultation_fee) — the fee is per-dentist (6.7).
DENTISTS = [
    ("Dr. Meera Prabhu", "meera.demo@clinic.local", "500.00"),
    ("Dr. Anil Kamath", "anil.demo@clinic.local", "300.00"),
]

_PNG = b"\x89PNG\r\n\x1a\n" + b"demo-xray-bytes" * 8


def _already_seeded(db) -> bool:
    count = db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "seed_demo")
    )
    return (count or 0) > 0


def seed_demo() -> None:
    rng = random.Random(7)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        if _already_seeded(db):
            print("seed_demo: already seeded (marker present), skipping.")
            return

        # --- dentists (staff_user rows for assignment/display) ---
        dentists = []
        for name, email, fee in DENTISTS:
            existing = db.scalar(select(StaffUser).where(StaffUser.email == email))
            if existing is None:
                d = StaffUser(
                    id=uuid4(),
                    name=name,
                    email=email,
                    roles=["dentist"],
                    active=True,
                    consultation_fee=Decimal(fee),
                )
                db.add(d)
                dentists.append(d)
            else:
                dentists.append(existing)
        db.flush()

        # --- priced catalogue: treatments + medicines (6.7) ---
        # `items` stays treatments-only: it feeds the procedure/invoice generation
        # below, and a demo bill of nothing but antibiotics would be odd.
        items = []
        for name, price in CATALOGUE:
            existing = db.scalar(
                select(TreatmentItem).where(
                    TreatmentItem.kind == "treatment", TreatmentItem.name == name
                )
            )
            if existing is None:
                it = TreatmentItem(
                    name=name, default_price=Decimal(price), kind="treatment"
                )
                db.add(it)
                items.append(it)
            else:
                items.append(existing)

        for name, price in MEDICINES:
            existing = db.scalar(
                select(TreatmentItem).where(
                    TreatmentItem.kind == "medicine", TreatmentItem.name == name
                )
            )
            if existing is None:
                db.add(
                    TreatmentItem(
                        name=name, default_price=Decimal(price), kind="medicine"
                    )
                )
        db.flush()

        # --- patients (reuse the existing generator; add if the table is thin) ---
        existing_patients = db.scalars(select(Patient)).all()
        if len(existing_patients) < 30:
            new_patients = generate_patients(count=50, seed=7)
            db.add_all(new_patients)
            db.flush()
            patients = list(existing_patients) + new_patients
        else:
            patients = list(existing_patients)

        active_patients = [p for p in patients if not p.archived]

        # --- appointments: past / today / future across statuses ---
        statuses_past = ["done", "done", "done", "cancelled", "no_show"]
        made_appts = 0
        for offset_days, statuses in (
            (-14, statuses_past),
            (-7, statuses_past),
            (0, ["arrived", "booked", "done"]),   # today
            (3, ["booked", "booked"]),
            (10, ["booked"]),
        ):
            base = now + timedelta(days=offset_days)
            for i, st in enumerate(statuses):
                patient = rng.choice(active_patients)
                primary = rng.choice(dentists)
                consulting = rng.choice(dentists) if rng.random() < 0.25 else None
                # Space slots through the clinic day (10:00, 10:45, …) to avoid overlap.
                start = base.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(minutes=45 * i)
                appt = Appointment(
                    patient_id=patient.id,
                    dentist_id=primary.id,
                    consulting_dentist_id=consulting.id if consulting else None,
                    start_time=start,
                    duration_min=30,
                    status=st,
                    reason=rng.choice(["Toothache", "Check-up", "Cleaning", "Follow-up", None]),
                )
                db.add(appt)
                made_appts += 1
        db.flush()

        # --- visits with procedures + invoices with payments (for ~12 patients) ---
        made_visits = made_invoices = 0
        for patient in rng.sample(active_patients, k=min(12, len(active_patients))):
            primary = rng.choice(dentists)
            consulting = rng.choice(dentists) if rng.random() < 0.3 else None

            treatment = Treatment(
                patient_id=patient.id,
                title=rng.choice(["RCT tooth 36", "Scaling", "Crown tooth 11", "Filling tooth 24"]),
                tooth_ref=rng.choice(["36", "11", "24", None]),
                status="completed" if rng.random() < 0.5 else "in_progress",
            )
            if treatment.status == "completed":
                treatment.closed_at = now - timedelta(days=rng.randint(1, 20))
            db.add(treatment)
            db.flush()

            visit = Visit(
                patient_id=patient.id,
                treatment_id=treatment.id,
                dentist_id=primary.id,
                consulting_dentist_id=consulting.id if consulting else None,
                visit_date=now - timedelta(days=rng.randint(1, 25)),
                complaint=rng.choice(["Pain on chewing", "Sensitivity", "Routine", "Swelling"]),
                clinical_notes="Demo visit — examined and treated.",
            )
            db.add(visit)
            db.flush()
            made_visits += 1

            chosen = rng.sample(items, k=rng.randint(1, 3))
            for it in chosen:
                db.add(ProcedurePerformed(visit_id=visit.id, treatment_item_id=it.id))
            db.flush()

            # Invoice from the procedures (mirrors the 5.2 generation logic).
            subtotal = sum((it.default_price for it in chosen), Decimal("0"))
            discount = Decimal("0")
            if rng.random() < 0.3:
                discount = (subtotal * Decimal("0.1")).quantize(Decimal("0.01"))
            total = subtotal - discount
            invoice = Invoice(
                patient_id=patient.id,
                visit_id=visit.id,
                subtotal=subtotal,
                discount=discount,
                total=total,
            )
            db.add(invoice)
            db.flush()
            for it in chosen:
                db.add(
                    InvoiceLine(
                        invoice_id=invoice.id,
                        treatment_item_id=it.id,
                        description=it.name,
                        amount=it.default_price,
                    )
                )

            # Payment: paid / partially paid / unpaid mix.
            roll = rng.random()
            if roll < 0.5:  # paid
                db.add(Payment(invoice_id=invoice.id, amount=total, mode=rng.choice(["cash", "upi", "card"])))
                invoice.status = "paid"
            elif roll < 0.8:  # partially paid
                part = (total / 2).quantize(Decimal("0.01"))
                db.add(Payment(invoice_id=invoice.id, amount=part, mode="cash"))
                invoice.status = "partially_paid"
            # else: unpaid (no payment row)
            db.flush()
            made_invoices += 1

        # --- a few file placeholders (metadata only; bytes written to storage) ---
        from app.services.storage import get_storage
        import io

        storage = get_storage()
        made_files = 0
        for patient in rng.sample(active_patients, k=min(5, len(active_patients))):
            key = storage.save(io.BytesIO(_PNG))
            db.add(
                PatientFile(
                    patient_id=patient.id,
                    uploaded_by=dentists[0].id,
                    kind="xray",
                    original_filename="demo-xray.png",
                    content_type="image/png",
                    size_bytes=len(_PNG),
                    caption="Demo X-ray",
                    storage_key=key,
                )
            )
            made_files += 1

        # --- lab work (6.6) --------------------------------------------------
        # Two labs plus a spread of cases that exercises every state the Lab tab
        # and the dashboard show: overdue, due soon, back-from-lab (undismissed),
        # already dealt with, and a cancelled one.
        db.flush()  # make sure the visits above have ids to link against

        labs = [
            Lab(name="Sri Dental Lab", phone="98800 11223", address="Davangere"),
            Lab(name="Precision Ceramics", phone="98800 44556", address="Bengaluru"),
        ]
        db.add_all(labs)
        db.flush()

        # Link cases to real visits so the "sent from this sitting" link is true.
        seeded_visits = list(
            db.scalars(
                select(Visit).order_by(Visit.visit_date.desc()).limit(6)
            ).all()
        )
        today = datetime.now(timezone.utc).date()
        # (days_since_sent, days_until_expected, status, follow_up_done, type)
        plan = [
            (12, -4, "sent", False, "crown"),          # overdue by 4 days
            (9, -1, "sent", False, "bridge"),          # overdue by 1
            (4, 3, "sent", False, "denture_partial"),  # due in 3 days
            (2, 6, "sent", False, "veneer"),           # due in 6
            (14, -6, "received", False, "crown"),      # back, needs calling in
            (20, -10, "received", True, "study_model"),# back and dealt with
            (8, -2, "cancelled", False, "inlay_onlay"),# scrapped
        ]
        made_lab_cases = 0
        for i, (sent_ago, due_in, status, done, stype) in enumerate(plan):
            if not seeded_visits:
                break
            visit = seeded_visits[i % len(seeded_visits)]
            sent_on = today - timedelta(days=sent_ago)
            db.add(
                LabCase(
                    patient_id=visit.patient_id,
                    lab_id=labs[i % len(labs)].id,
                    visit_id=visit.id,
                    appointment_id=visit.appointment_id,
                    sample_type=stype,
                    tooth_ref=rng.choice(["36", "11", "46", None]),
                    sent_date=sent_on,
                    expected_date=today + timedelta(days=due_in),
                    received_date=(today + timedelta(days=due_in)) if status == "received" else None,
                    status=status,
                    follow_up_done=done,
                    created_by=dentists[0].id,
                    notes="Shade A2" if stype in {"crown", "veneer", "bridge"} else None,
                )
            )
            made_lab_cases += 1

        # Marker so re-runs are no-ops.
        record_audit(
            db,
            actor_id=None,
            action="seed_demo",
            entity="demo",
            entity_id=None,
            details={
                "marker": _DEMO_MARKER,
                "dentists": len(dentists),
                "appointments": made_appts,
                "visits": made_visits,
                "invoices": made_invoices,
                "files": made_files,
                "lab_cases": made_lab_cases,
            },
        )
        db.commit()

    print(
        f"seed_demo: {len(dentists)} dentists, {len(items)} catalogue items, "
        f"{made_appts} appointments, {made_visits} visits, {made_invoices} invoices, "
        f"{made_files} files, {made_lab_cases} lab cases. Sign in as the admin to browse."
    )


if __name__ == "__main__":
    seed_demo()
