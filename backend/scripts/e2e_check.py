"""End-to-end check — walk the clinic's real workflow through the real API.

    docker compose run --rm -v "${PWD}\\backend:/app" backend python -m scripts.e2e_check

This is NOT a replacement for the pytest suite. The unit/endpoint tests prove each
rule in isolation; this walks the whole day the way the clinic does — book, arrive,
treat, chart, bill, take payment, send to the lab, get it back, recall — and checks
that each step leaves the app in the state the NEXT step assumes. Step 6.8 found
eight real problems that way, none of which a single-endpoint test would have caught.

Made permanent in 6.13. Two earlier versions of this script (6.9, 6.11) were
throwaways that no longer exist, so every later step had to rebuild the harness
before it could check anything.

WHAT IT DOES TO YOUR DATA
    It creates its own patient, staff, catalogue items and lab, then deletes them
    on the way out (`--keep` skips the cleanup if you want to inspect the result).
    It does not touch seeded demo data. Run it against the dev compose DB, never
    against anything real.

AUTH
    Auth is overridden, not performed: `app.dependency_overrides[get_current_claims]`
    is pointed at a staff row, exactly as the pytest suite does. That lets the script
    switch roles mid-walk (`as_role("receptionist")`) to prove the 6.12 money split.

    *** The override is cleared ONCE, at the very end, in a finally block. ***
    In 6.11 checks were appended after a mid-script teardown and every one of them
    silently 401'd — they looked like endpoint failures and were not. If you add
    checks, add them BEFORE the cleanup, never after.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import get_current_claims
from app.db import SessionLocal
from app.main import app
from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.lab import Lab
from app.models.lab_case import LabCase
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.procedure_performed import ProcedurePerformed
from app.models.staff_user import StaffUser
from app.models.tooth_condition import ToothCondition
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit

client = TestClient(app)

# --- tiny check harness ------------------------------------------------------

_passed = 0
_failures: list[str] = []
_section = ""


def section(name: str) -> None:
    global _section
    _section = name
    print(f"\n--- {name}")


def check(label: str, condition: bool, detail: str = "") -> bool:
    """Record one assertion. Never raises — a failed check must not hide later ones."""
    global _passed
    if condition:
        _passed += 1
        print(f"  ok   {label}")
    else:
        msg = f"[{_section}] {label}" + (f" — {detail}" if detail else "")
        _failures.append(msg)
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
    return condition


def as_role(staff_by_role: dict[str, StaffUser], role: str) -> None:
    """Switch which staff row the API thinks is signed in."""
    staff = staff_by_role[role]
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}


# --- fixtures ----------------------------------------------------------------

TAG = f"e2e-{uuid.uuid4().hex[:8]}"


def build_fixtures(db) -> dict:
    """Create the staff, patient, catalogue and lab this walk needs."""
    staff_by_role = {}
    for role, roles in [
        ("receptionist", ["receptionist"]),
        ("dentist", ["dentist"]),
        ("admin", ["dentist", "admin"]),  # the owner holds both (BUILD_PLAN §2)
    ]:
        s = StaffUser(
            id=uuid.uuid4(),
            name=f"{TAG} {role}",
            email=f"{TAG}-{role}@e2e.local",
            roles=roles,
            active=True,
            consultation_fee="300.00" if role == "dentist" else None,
        )
        db.add(s)
        staff_by_role[role] = s

    patient = Patient(
        name=f"{TAG} Patient",
        phone="9000000000",
        date_of_birth=date(1990, 5, 17),
        medical_notes="Penicillin allergy",
    )
    rct = TreatmentItem(name=f"{TAG} RCT", default_price="4000.00")
    scaling = TreatmentItem(name=f"{TAG} Scaling", default_price="1500.00")
    medicine = TreatmentItem(
        name=f"{TAG} Amoxicillin", default_price="45.00", kind="medicine"
    )
    lab = Lab(name=f"{TAG} Lab", phone="9111111111")
    db.add_all([patient, rct, scaling, medicine, lab])
    db.commit()

    for obj in [*staff_by_role.values(), patient, rct, scaling, medicine, lab]:
        db.refresh(obj)

    return {
        "staff": staff_by_role,
        "patient": patient,
        "rct": rct,
        "scaling": scaling,
        "medicine": medicine,
        "lab": lab,
    }


def cleanup(db, fx: dict) -> None:
    """Delete everything this run created, children first."""
    patient_id = fx["patient"].id
    staff_ids = [s.id for s in fx["staff"].values()]

    visit_ids = [v.id for v in db.scalars(select(Visit).where(Visit.patient_id == patient_id))]
    invoice_ids = (
        [i.id for i in db.scalars(select(Invoice).where(Invoice.visit_id.in_(visit_ids)))]
        if visit_ids
        else []
    )

    def wipe(stmt):
        for row in db.scalars(stmt):
            db.delete(row)
        db.commit()

    if invoice_ids:
        wipe(select(Payment).where(Payment.invoice_id.in_(invoice_ids)))
        wipe(select(InvoiceLine).where(InvoiceLine.invoice_id.in_(invoice_ids)))
        wipe(select(Invoice).where(Invoice.id.in_(invoice_ids)))
    wipe(select(LabCase).where(LabCase.patient_id == patient_id))
    wipe(select(ToothCondition).where(ToothCondition.patient_id == patient_id))
    if visit_ids:
        wipe(select(ProcedurePerformed).where(ProcedurePerformed.visit_id.in_(visit_ids)))
    # Visits BEFORE appointments: visit.appointment_id is a real FK, so deleting the
    # appointment first is a ForeignKeyViolation. Same reason treatments come last.
    wipe(select(Visit).where(Visit.patient_id == patient_id))
    wipe(select(Appointment).where(Appointment.patient_id == patient_id))
    wipe(select(Treatment).where(Treatment.patient_id == patient_id))
    wipe(select(AuditLog).where(AuditLog.actor_id.in_(staff_ids)))
    wipe(select(Patient).where(Patient.id == patient_id))
    wipe(select(LabCase).where(LabCase.lab_id == fx["lab"].id))
    wipe(select(Lab).where(Lab.id == fx["lab"].id))
    wipe(
        select(TreatmentItem).where(
            TreatmentItem.id.in_([fx["rct"].id, fx["scaling"].id, fx["medicine"].id])
        )
    )
    wipe(select(StaffUser).where(StaffUser.id.in_(staff_ids)))


# --- the walk ----------------------------------------------------------------


def run(fx: dict) -> None:
    staff = fx["staff"]
    patient_id = str(fx["patient"].id)
    dentist_id = str(staff["dentist"].id)

    # 1. The front desk opens the day ----------------------------------------
    section("Front desk — patients")
    as_role(staff, "receptionist")

    check("health is up", client.get("/health").status_code == 200)

    me = client.get("/me")
    check("/me identifies the signed-in staff", me.status_code == 200)
    check("/me carries roles as a list", isinstance(me.json().get("roles"), list))

    found = client.get("/patients", params={"q": TAG})
    check("patient search finds our patient", found.status_code == 200)
    check(
        "search NARROWS (not everyone)",
        all(TAG in p["name"] for p in found.json()["items"]),
        "a filter that returns everything is the 6.8 bug",
    )

    prof = client.get(f"/patients/{patient_id}")
    check("patient profile loads", prof.status_code == 200)
    check("age is computed from DOB", isinstance(prof.json().get("age"), int))
    check("medical notes survive", bool(prof.json().get("medical_notes")))

    # 2. Booking --------------------------------------------------------------
    section("Booking")
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1, hours=2)
    booked = client.post(
        "/appointments",
        json={
            "patient_id": patient_id,
            "dentist_id": dentist_id,
            "start_time": start.isoformat(),
            "duration_min": 30,
        },
    )
    check("appointment books", booked.status_code == 201, booked.text[:200])
    appt = booked.json()
    appt_id = appt["id"]
    check("appointment gets a readable number", isinstance(appt.get("number"), int))
    check("new appointment starts 'booked'", appt["status"] == "booked")

    clash = client.post(
        "/appointments",
        json={
            "patient_id": patient_id,
            "dentist_id": dentist_id,
            "start_time": start.isoformat(),
            "duration_min": 30,
        },
    )
    check(
        "double-booking the same dentist is refused",
        clash.status_code == 409,
        f"got {clash.status_code} — the GiST constraint is the real guarantee",
    )

    by_patient = client.get("/appointments", params={"patient_id": patient_id})
    check("appointments filter by patient", by_patient.status_code == 200)
    check(
        "patient filter NARROWS",
        all(a["patient_id"] == patient_id for a in by_patient.json()["items"]),
    )

    arrived = client.post(f"/appointments/{appt_id}/status", json={"status": "arrived"})
    check("patient can be marked arrived", arrived.status_code == 200)
    bad = client.post(f"/appointments/{appt_id}/status", json={"status": "booked"})
    check("illegal status transition is refused", bad.status_code == 409)

    # 3. Chairside — the dentist records the visit ----------------------------
    section("Chairside — visit + OPD record")
    as_role(staff, "dentist")

    visit = client.post(
        "/visits",
        json={
            "patient_id": patient_id,
            "appointment_id": appt_id,
            "treatment": {"title": f"{TAG} RCT tooth 36", "tooth_ref": "36"},
            "treatment_status": "in_progress",
            "dentist_id": dentist_id,
            "complaint": "Pain on chewing, lower left",
            "procedures": [{"treatment_item_id": str(fx["rct"].id), "tooth_ref": "36"}],
            "bp_systolic": 120,
            "bp_diastolic": 80,
            "intra_oral": "Deep caries 36",
            "investigations": ["iopa"],
            "provisional_diagnosis": "Irreversible pulpitis 36",
            "final_diagnosis": "Irreversible pulpitis 36",
        },
    )
    check("visit records", visit.status_code == 201, visit.text[:300])
    v = visit.json()
    visit_id = v["id"]
    treatment_id = v["treatment_id"]
    check("visit gets a V- number", isinstance(v.get("number"), int))
    check("diagnosis is stored", v.get("final_diagnosis") == "Irreversible pulpitis 36")
    check("investigations round-trip as an array", v.get("investigations") == ["iopa"])

    after = client.get(f"/appointments/{appt_id}").json()
    check(
        "recording a visit AUTO-CLOSES its appointment",
        after["status"] == "done",
        f"status is {after['status']} — the 6.8 rule",
    )

    # 4. The chart ------------------------------------------------------------
    section("Dental chart (append-only)")
    marked = client.post(
        f"/patients/{patient_id}/chart",
        json={"entries": [{"tooth": "36", "condition": "caries", "surfaces": "MOD"}],
              "visit_id": visit_id},
    )
    check("tooth can be marked", marked.status_code == 201, marked.text[:200])

    # "root_canal", not "root_canal_treated" — the vocabulary is a Literal in
    # schemas/chart.py, so a wrong name is a 422 rather than a silent no-op.
    remarked = client.post(
        f"/patients/{patient_id}/chart",
        json={"entries": [{"tooth": "36", "condition": "root_canal"}],
              "visit_id": visit_id},
    )
    check("tooth can be re-marked", remarked.status_code == 201, remarked.text[:200])

    chart = client.get(f"/patients/{patient_id}/chart").json()
    current = [i for i in chart["items"] if i["tooth"] == "36"]
    check(
        "current chart shows ONE row for tooth 36",
        len(current) == 1,
        f"got {len(current)} — superseded rows must not show as current",
    )
    check(
        "the current row is the NEW condition",
        bool(current) and current[0]["condition"] == "root_canal",
    )

    hist = client.get(f"/patients/{patient_id}/chart/36/history")
    check("tooth history is readable", hist.status_code == 200)
    check(
        "the PRE-treatment finding survives as history",
        any(i["condition"] == "caries" for i in hist.json()["items"]),
        "an overwrite would destroy the medico-legal record",
    )

    # 5. Multi-visit treatment threading --------------------------------------
    section("Treatment threading")
    phase = client.post(f"/treatments/{treatment_id}/phase", json={"phase": 2})
    check("treatment phase can be set", phase.status_code == 200, phase.text[:200])
    check(
        "bare PATCH /treatments/{id} stays 405",
        client.patch(f"/treatments/{treatment_id}", json={"title": "x"}).status_code == 405,
        "no general replace route — writes are explicit actions",
    )

    visit2 = client.post(
        "/visits",
        json={
            "patient_id": patient_id,
            "treatment_id": treatment_id,
            "treatment_status": "completed",
            "dentist_id": dentist_id,
            "complaint": "Obturation",
            "procedures": [{"treatment_item_id": str(fx["medicine"].id)}],
        },
    )
    check("second sitting threads onto the same treatment", visit2.status_code == 201)
    visit2_id = visit2.json()["id"]

    thread = client.get("/visits", params={"treatment_id": treatment_id}).json()
    check("both sittings hang off one treatment", thread["total"] >= 2)

    closed = client.get(f"/treatments/{treatment_id}").json()
    check("finishing the last sitting closed the treatment", closed["status"] == "completed")
    check("closed_at is stamped", closed.get("closed_at") is not None)

    # 6. Billing — front desk -------------------------------------------------
    section("Billing")
    as_role(staff, "receptionist")

    unbilled = client.get("/visits/unbilled")
    check("unbilled worklist loads", unbilled.status_code == 200)
    check(
        "our fresh visit is on the unbilled worklist",
        any(x["id"] == visit_id for x in unbilled.json()["items"]),
    )

    inv = client.post(
        f"/visits/{visit_id}/invoice",
        json={"extra_lines": [{"description": "Consultation", "amount": "300.00"}]},
    )
    check("receptionist can generate an invoice", inv.status_code == 201, inv.text[:300])
    invoice = inv.json()
    invoice_id = invoice["id"]
    check(
        "invoice total = procedures + custom line",
        invoice["total"] == "4300.00",
        f"got {invoice['total']} (expected 4000 RCT + 300 consult)",
    )

    dup = client.post(f"/visits/{visit_id}/invoice", json={})
    check("a second invoice for the same visit is refused", dup.status_code == 409)

    pay1 = client.post(
        f"/invoices/{invoice_id}/payments", json={"amount": "1000.00", "mode": "cash"}
    )
    check("payment records", pay1.status_code == 201, pay1.text[:200])
    check("status derives to partially_paid", pay1.json()["status"] == "partially_paid")
    check("outstanding is correct", pay1.json()["outstanding"] == "3300.00")

    pay2 = client.post(
        f"/invoices/{invoice_id}/payments", json={"amount": "3300.00", "mode": "upi"}
    )
    check("invoice settles to paid", pay2.json()["status"] == "paid")
    check("outstanding floors at zero", pay2.json()["outstanding"] == "0.00")

    ledger = client.get("/invoices", params={"patient_id": patient_id})
    check("invoice ledger filters by patient", ledger.status_code == 200)
    check(
        "invoice patient filter NARROWS",
        all(i["patient_id"] == patient_id for i in ledger.json()["items"]),
        "this exact filter silently returned EVERY invoice before 6.8",
    )

    # 7. Lab ------------------------------------------------------------------
    section("Lab")
    case = client.post(
        "/lab-cases",
        json={
            "patient_id": patient_id,
            "lab_id": str(fx["lab"].id),
            "visit_id": visit2_id,
            "sample_type": "crown",
            "sent_date": date.today().isoformat(),
            "expected_date": (date.today() + timedelta(days=5)).isoformat(),
            "tooth_ref": "36",
        },
    )
    check("lab case can be sent", case.status_code == 201, case.text[:300])
    case_id = case.json()["id"]
    check("lab case gets an L- number", isinstance(case.json().get("number"), int))
    check("lab case starts 'sent'", case.json()["status"] == "sent")

    recv = client.post(f"/lab-cases/{case_id}/received", json={})
    check("lab case can be received", recv.status_code == 200, recv.text[:200])
    check("received case is 'received'", recv.json()["status"] == "received")

    dash = client.get("/lab-cases/dashboard")
    check("lab dashboard loads", dash.status_code == 200)

    done = client.post(f"/lab-cases/{case_id}/follow-up-done", json={"done": True})
    check("lab follow-up can be dismissed", done.status_code == 200)

    # 8. Recall ---------------------------------------------------------------
    section("Recall")
    client.patch(
        f"/patients/{patient_id}",
        json={"recall_due": (date.today() - timedelta(days=1)).isoformat()},
    )
    recalls = client.get("/patients/recalls-due")
    check("recalls-due loads", recalls.status_code == 200)
    check(
        "an overdue patient appears on the recall list",
        any(p["id"] == patient_id for p in recalls.json()["items"]),
    )

    # 9. The 6.12 money split -------------------------------------------------
    section("Money is admin-only (6.12)")
    for role in ("receptionist", "dentist"):
        as_role(staff, role)
        check(f"{role} is refused /reports", client.get("/reports").status_code == 403)
        check(
            f"{role} is refused today's collections",
            client.get("/invoices/collections").status_code == 403,
        )
        check(
            f"{role} can STILL read an invoice (billing is front-desk)",
            client.get(f"/invoices/{invoice_id}").status_code == 200,
        )

    as_role(staff, "admin")
    check("admin sees /reports", client.get("/reports").status_code == 200)
    coll = client.get("/invoices/collections")
    check("admin sees today's collections", coll.status_code == 200)
    check(
        "collections carries all three modes",
        coll.status_code == 200 and set(coll.json()["by_mode"]) == {"cash", "card", "upi"},
    )
    rep = client.get("/reports")
    check(
        "reports bundle has all four blocks",
        rep.status_code == 200
        and set(rep.json()) == {"revenue_trend", "procedure_mix", "no_show", "by_dentist"},
    )

    # 10. Clinical writes stay dentist-gated ----------------------------------
    section("Clinical writes stay role-split")
    as_role(staff, "receptionist")
    denied = client.post(
        "/visits",
        json={
            "patient_id": patient_id,
            "treatment": {"title": "should not work"},
            "treatment_status": "in_progress",
            "procedures": [],
        },
    )
    check("receptionist cannot record a visit", denied.status_code == 403)
    check(
        "receptionist cannot write the chart",
        client.post(
            f"/patients/{patient_id}/chart",
            json={"entries": [{"tooth": "11", "condition": "caries"}]},
        ).status_code
        == 403,
    )
    check(
        "receptionist cannot edit the price list",
        client.post(
            "/treatment-items", json={"name": f"{TAG} nope", "default_price": "1.00"}
        ).status_code
        == 403,
    )

    # 11. Soft delete ---------------------------------------------------------
    section("Soft delete")
    arch = client.post(f"/patients/{patient_id}/archive")
    check("patient archives", arch.status_code == 200)
    check("archived patient is still readable (retention)",
          client.get(f"/patients/{patient_id}").status_code == 200)

    # 6.13: an archived record is retained but not added to — the rule
    # patient_files.py has had since 5.6, now applied to booking and visits too.
    check(
        "archived patient cannot be booked",
        client.post(
            "/appointments",
            json={"patient_id": patient_id, "start_time": "2099-01-01T10:00:00+00:00",
                  "duration_min": 30},
        ).status_code == 409,
    )
    as_role(staff, "dentist")
    check(
        "archived patient cannot have a visit recorded",
        client.post(
            "/visits",
            json={"patient_id": patient_id, "treatment": {"title": "nope"},
                  "treatment_status": "completed", "procedures": []},
        ).status_code == 409,
    )
    as_role(staff, "receptionist")

    client.post(f"/patients/{patient_id}/unarchive")
    check("patient can be restored",
          client.get(f"/patients/{patient_id}").json()["archived"] is False)
    check(
        "restoring makes booking work again (soft block, not a dead end)",
        client.post(
            "/appointments",
            json={"patient_id": patient_id, "start_time": "2099-01-01T10:00:00+00:00",
                  "duration_min": 30},
        ).status_code == 201,
    )

    # 6.13: the search box must treat LIKE wildcards as characters. Compared
    # against the unfiltered count, not zero — other patients may legitimately
    # have a '%' in their name, and an absolute number would flake.
    section("Search treats wildcards literally (6.13)")
    everyone = client.get("/patients").json()["total"]
    check(
        "q='%' does not return every patient",
        client.get("/patients", params={"q": "%"}).json()["total"] < everyone,
        "unescaped, '%' is a LIKE wildcard and matched the whole table",
    )
    check(
        "q='_' does not match any single character",
        client.get("/patients", params={"q": "_"}).json()["total"] < everyone,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep", action="store_true", help="don't delete the data this run created"
    )
    args = parser.parse_args()

    print(f"e2e_check — tag {TAG}")
    db = SessionLocal()
    fx = build_fixtures(db)
    try:
        run(fx)
    finally:
        # ONE teardown, at the very end. See the module docstring — clearing the
        # override mid-script silently 401s every later check.
        app.dependency_overrides.clear()
        if args.keep:
            print(f"\n--keep: leaving {TAG} data in the database")
        else:
            cleanup(db, fx)
            print(f"\ncleaned up {TAG}")
        db.close()

    total = _passed + len(_failures)
    print(f"\n{'=' * 60}")
    if _failures:
        print(f"{_passed}/{total} checks passed — {len(_failures)} FAILED:\n")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"{_passed}/{total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
