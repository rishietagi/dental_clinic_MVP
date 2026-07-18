"""Seed ~50 fake patients for local development.

    python -m app.seed_patients

Fake data only — never real patient data on a dev machine (that's Phase 7+).
Idempotent: if the seed set is already present it does nothing, so re-running is
safe. Uses only the standard library (no faker) — a curated pool of Indian names
fits this Davangere clinic.

Split into a pure generator (generate_patients, unit-testable, no DB) and the DB
seeder (seed_patients, with the idempotency guard + a single summary audit row).
"""

import random
from datetime import date, timedelta

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.patient import Patient
from app.services.audit import record_audit

SEED_COUNT = 50

# Curated pools — Karnataka/Davangere-plausible. Kept small but varied; random
# first+last gives ample combinations for 50 rows.
FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karan", "Nikhil", "Rahul",
    "Suresh", "Manoj", "Prakash", "Ganesh", "Kiran", "Vinay", "Harish",
    "Ananya", "Priya", "Divya", "Sneha", "Kavya", "Meena", "Lakshmi", "Deepa",
    "Pooja", "Shwetha", "Asha", "Rekha", "Geetha", "Nandini", "Sushma",
]
LAST_NAMES = [
    "Rao", "Shetty", "Gowda", "Hegde", "Nayak", "Patil", "Kulkarni", "Desai",
    "Iyer", "Nair", "Reddy", "Kamath", "Bhat", "Prabhu", "Shenoy", "Murthy",
    "Naik", "Pai", "Acharya", "Rai", "Kumar", "Singh", "Mehta", "Shah", "Jain",
]
GENDERS = ["Male", "Female"]

MEDICAL_NOTES = [
    "Diabetic (Type 2).",
    "On blood thinners — caution before any extraction.",
    "Penicillin allergy.",
    "Hypertension — monitor before procedures.",
    "Asthmatic; carries an inhaler.",
    "Pregnant (2nd trimester) — avoid X-rays.",
]


def _random_phone(rng: random.Random) -> str:
    """A plausible Indian mobile: +91 then 10 digits starting 6–9."""
    first = rng.choice("6789")
    rest = "".join(rng.choice("0123456789") for _ in range(9))
    return f"+91{first}{rest}"


def _random_dob(rng: random.Random) -> date:
    """A DOB giving an age roughly 5–85 years."""
    age_days = rng.randint(5 * 365, 85 * 365)
    return date.today() - timedelta(days=age_days)


def generate_patients(count: int = SEED_COUNT, seed: int = 42) -> list[Patient]:
    """Build `count` unsaved Patient objects. Pure — no DB, deterministic per seed.

    ~20% get medical_notes (so the profile banner is visible in the seed set) and
    ~10% are archived (so the archived filter has something to hide).
    """
    rng = random.Random(seed)
    patients: list[Patient] = []
    for _ in range(count):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        patients.append(
            Patient(
                name=name,
                phone=_random_phone(rng),
                date_of_birth=_random_dob(rng),
                gender=rng.choice(GENDERS),
                medical_notes=rng.choice(MEDICAL_NOTES) if rng.random() < 0.20 else None,
                archived=rng.random() < 0.10,
            )
        )
    return patients


def seed_patients() -> None:
    with SessionLocal() as session:
        existing = session.scalar(select(func.count()).select_from(Patient)) or 0
        if existing >= SEED_COUNT:
            print(f"seed: already seeded ({existing} patients present), skipping.")
            return

        patients = generate_patients()
        session.add_all(patients)

        # One summary audit row for the whole bulk seed (not one per patient).
        record_audit(
            session,
            actor_id=None,
            action="seed",
            entity="patient",
            entity_id=None,
            details={"count": SEED_COUNT},
        )
        session.commit()

    print(f"seed: inserted {SEED_COUNT} fake patients.")
    print("seed: audit_log summary entry written (action=seed, entity=patient).")


if __name__ == "__main__":
    seed_patients()
