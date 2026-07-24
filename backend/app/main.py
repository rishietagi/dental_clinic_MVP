"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    appointments,
    auth,
    clinic_settings,
    invoices,
    patient_files,
    patients,
    reports,
    staff,
    treatment_items,
    treatments,
    visits,
)

app = FastAPI(title="Dental Clinic Management System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clinic_settings.router)
app.include_router(patients.router)
app.include_router(appointments.router)
app.include_router(treatment_items.router)
app.include_router(treatments.router)
app.include_router(visits.router)
app.include_router(invoices.router)
app.include_router(patient_files.router)
app.include_router(reports.router)
app.include_router(staff.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
