"""One-off top-up: add the 6.7 pricing demo data to an already-seeded demo DB.

`seed_demo` is marker-guarded (re-runs are no-ops), so a DB seeded before 6.7 has
no medicines and no consultation fees — the two new Pricing tabs would open
empty. This adds just those rows.

Idempotent: medicines are matched by (kind, name), and a dentist that already has
a fee is left alone. Safe to run twice.

Delete this script once it has served its purpose (as with `seed_labs_topup`).

    docker compose run --rm backend python -m app.seed_pricing_topup
"""

from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models.staff_user import StaffUser
from app.models.treatment_item import TreatmentItem

# A small, realistic set of what a dental clinic dispenses at the chair.
MEDICINES = [
    ("Amoxicillin 500mg", "45.00"),
    ("Metronidazole 400mg", "35.00"),
    ("Ibuprofen 400mg", "25.00"),
    ("Paracetamol 650mg", "20.00"),
    ("Chlorhexidine mouthwash", "150.00"),
    ("Lignocaine gel", "90.00"),
]

# Fee assigned to dentists that don't have one yet, in listing order.
CONSULTATION_FEES = ["300.00", "500.00"]


def main() -> None:
    with SessionLocal() as db:
        added_meds = 0
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
                added_meds += 1

        dentists = list(
            db.scalars(
                select(StaffUser)
                .where(StaffUser.roles.any("dentist"), StaffUser.active.is_(True))
                .order_by(StaffUser.name)
            ).all()
        )
        priced = 0
        for i, dentist in enumerate(dentists):
            if dentist.consultation_fee is None:
                dentist.consultation_fee = Decimal(
                    CONSULTATION_FEES[i % len(CONSULTATION_FEES)]
                )
                priced += 1

        db.commit()
        print(
            f"added {added_meds} medicine(s); "
            f"set a consultation fee on {priced} of {len(dentists)} dentist(s)"
        )


if __name__ == "__main__":
    main()
