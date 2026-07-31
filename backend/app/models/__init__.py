"""SQLAlchemy declarative base.

Every model inherits from Base. Base.metadata is the in-code description of all
tables — Alembic compares it against the live database to generate migrations.

Models must be IMPORTED here so they register on Base.metadata by the time
Alembic's env.py runs; otherwise --autogenerate sees an empty schema. Import them
at the bottom (after Base is defined) to avoid a circular import.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Register models on Base.metadata. Keep after Base so the modules can import it.
from app.models.staff_user import StaffUser  # noqa: E402,F401
from app.models.audit_log import AuditLog  # noqa: E402,F401
from app.models.patient import Patient  # noqa: E402,F401
from app.models.appointment import Appointment  # noqa: E402,F401
from app.models.treatment_item import TreatmentItem  # noqa: E402,F401
from app.models.treatment import Treatment  # noqa: E402,F401
from app.models.visit import Visit  # noqa: E402,F401
from app.models.procedure_performed import ProcedurePerformed  # noqa: E402,F401
from app.models.clinic_settings import ClinicSettings  # noqa: E402,F401
from app.models.invoice import Invoice  # noqa: E402,F401
from app.models.invoice_line import InvoiceLine  # noqa: E402,F401
from app.models.payment import Payment  # noqa: E402,F401
from app.models.patient_file import PatientFile  # noqa: E402,F401
from app.models.lab import Lab  # noqa: E402,F401
from app.models.lab_case import LabCase  # noqa: E402,F401
from app.models.tooth_condition import ToothCondition  # noqa: E402,F401
