"""One-off top-up: add the 6.6 lab demo data to an already-seeded demo DB.

seed_demo is marker-guarded (re-runs are no-ops), so a DB seeded before 6.6 has no
labs. This adds just the lab rows, and is itself a no-op if labs already exist.
"""
from datetime import datetime, timedelta, timezone
import random

from sqlalchemy import select

from app.db import SessionLocal
from app.models.lab import Lab
from app.models.lab_case import LabCase
from app.models.staff_user import StaffUser
from app.models.visit import Visit


def main() -> None:
    rng = random.Random(6006)
    with SessionLocal() as db:
        if db.scalar(select(Lab).limit(1)) is not None:
            print("labs already present — nothing to do")
            return

        labs = [
            Lab(name="Sri Dental Lab", phone="98800 11223", address="Davangere"),
            Lab(name="Precision Ceramics", phone="98800 44556", address="Bengaluru"),
        ]
        db.add_all(labs)
        db.flush()

        dentist = db.scalar(select(StaffUser).where(StaffUser.roles.any("dentist")))
        visits = list(db.scalars(select(Visit).order_by(Visit.visit_date.desc()).limit(6)).all())
        today = datetime.now(timezone.utc).date()
        plan = [
            (12, -4, "sent", False, "crown"),
            (9, -1, "sent", False, "bridge"),
            (4, 3, "sent", False, "denture_partial"),
            (2, 6, "sent", False, "veneer"),
            (14, -6, "received", False, "crown"),
            (20, -10, "received", True, "study_model"),
            (8, -2, "cancelled", False, "inlay_onlay"),
        ]
        made = 0
        for i, (sent_ago, due_in, status, done, stype) in enumerate(plan):
            if not visits:
                break
            v = visits[i % len(visits)]
            db.add(
                LabCase(
                    patient_id=v.patient_id,
                    lab_id=labs[i % len(labs)].id,
                    visit_id=v.id,
                    appointment_id=v.appointment_id,
                    sample_type=stype,
                    tooth_ref=rng.choice(["36", "11", "46", None]),
                    sent_date=today - timedelta(days=sent_ago),
                    expected_date=today + timedelta(days=due_in),
                    received_date=(today + timedelta(days=due_in)) if status == "received" else None,
                    status=status,
                    follow_up_done=done,
                    created_by=dentist.id if dentist else None,
                    notes="Shade A2" if stype in {"crown", "veneer", "bridge"} else None,
                )
            )
            made += 1
        db.commit()
        print(f"seeded {len(labs)} labs and {made} lab cases")


if __name__ == "__main__":
    main()
