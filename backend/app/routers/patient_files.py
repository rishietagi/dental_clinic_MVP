"""Patient file endpoints — X-rays, photos, documents (step 5.6).

Makes the app a real clinical record: a dentist attaches a radiograph/photo/scan
to a patient. Opaque storage — the bytes live on disk (a Docker volume in dev,
swappable for cloud in Phase 7 via `services/storage`), the DB keeps metadata.

Role split, matching visits (BUILD_PLAN §2 — clinical records are the dentist's):
- **Upload / archive** — `require_role("dentist","admin")`. Adding an X-ray is a
  clinical act.
- **List / view** — any active staff. The receptionist may need to pull up a file.

**One upload = one transaction with the bytes.** The bytes are written to storage
first (so the row never references a missing file); then the metadata row + an
audit row commit together. If the DB commit fails, the orphaned bytes are cleaned
up. Validation (content-type allowlist, size cap) happens BEFORE anything is
written, so a rejected upload leaves nothing behind.

No patient id in the content URL (`/files/{id}/content`) — the no-PII-in-URL rule;
the bytes are still auth-guarded. Files soft-delete (archive), never hard-delete —
medico-legal retention, like patients.
"""

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_staff, require_role
from app.config import settings
from app.db import get_db
from app.models.patient import Patient
from app.models.patient_file import PatientFile
from app.models.staff_user import StaffUser
from app.schemas.patient_file import FileKind, PatientFileList, PatientFileRead
from app.services.audit import record_audit
from app.services.storage import get_storage

router = APIRouter(tags=["patient-files"])

# Images (for inline preview) + PDF (the common scanned-document format). An
# opaque allowlist — we don't inspect the bytes, just gate the declared type.
_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
}


def _patient_or_404(db: Session, patient_id: UUID) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
        )
    return patient


@router.post(
    "/patients/{patient_id}/files",
    response_model=PatientFileRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_file(
    patient_id: UUID,
    file: UploadFile = File(...),
    kind: FileKind = Form(...),
    caption: str | None = Form(default=None),
    visit_id: UUID | None = Form(default=None),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("dentist", "admin")),
) -> PatientFileRead:
    """Upload a file for a patient. Multipart: the file plus kind/caption/visit_id.

    Validates type + size before writing anything. Uploading against an archived
    patient is refused (their record is retained but not actively edited).
    """
    patient = _patient_or_404(db, patient_id)
    if patient.archived:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot upload files for an archived patient.",
        )

    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only images (JPEG/PNG/WebP/GIF) and PDF files are accepted.",
        )

    # Enforce the size cap. UploadFile buffers to a SpooledTemporaryFile, so
    # seeking to the end gives the size without loading it all into memory.
    file.file.seek(0, 2)  # SEEK_END
    size_bytes = file.file.tell()
    file.file.seek(0)
    if size_bytes > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,  # Content Too Large
            detail=f"File is too large (max {settings.max_upload_bytes // (1024 * 1024)} MB).",
        )

    # Bytes first, so the row never points at a missing file.
    storage = get_storage()
    storage_key = storage.save(file.file)

    try:
        record = PatientFile(
            patient_id=patient_id,
            visit_id=visit_id,
            uploaded_by=staff.id,
            kind=kind,
            original_filename=file.filename or "upload",
            content_type=file.content_type,
            size_bytes=size_bytes,
            caption=caption,
            storage_key=storage_key,
        )
        db.add(record)
        db.flush()

        record_audit(
            db,
            actor_id=staff.id,
            action="create",
            entity="patient_file",
            entity_id=record.id,
            details=jsonable_encoder(
                {
                    "patient_id": patient_id,
                    "kind": kind,
                    "filename": record.original_filename,
                    "size_bytes": size_bytes,
                }
            ),
        )
        db.commit()
    except Exception:
        # The metadata never landed — don't leak the orphaned bytes.
        db.rollback()
        storage.delete(storage_key)
        raise

    db.refresh(record)
    return PatientFileRead.model_validate(record)


@router.get("/patients/{patient_id}/files", response_model=PatientFileList)
def list_files(
    patient_id: UUID,
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> PatientFileList:
    """A patient's files, newest first. Archived hidden unless asked."""
    _patient_or_404(db, patient_id)

    base = select(PatientFile).where(PatientFile.patient_id == patient_id)
    if not include_archived:
        base = base.where(PatientFile.archived.is_(False))

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(PatientFile.created_at.desc())).all()
    return PatientFileList(
        items=[PatientFileRead.model_validate(r) for r in rows],
        total=total,
    )


@router.get("/files/{file_id}/content")
def get_file_content(
    file_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> StreamingResponse:
    """Stream a file's bytes with its stored Content-Type.

    Any active staff — but still auth-guarded (no anonymous access to clinical
    images). Archived files are still fetchable by id, so historical records that
    reference them keep working. `inline` so images preview in the browser; the
    frontend adds a download action for documents.
    """
    record = db.get(PatientFile, file_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
        )

    storage = get_storage()
    try:
        stream = storage.open(record.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File contents are missing."
        ) from exc

    return StreamingResponse(
        stream,
        media_type=record.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{record.original_filename}"'
        },
    )


@router.post("/files/{file_id}/archive", response_model=PatientFileRead)
def archive_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("dentist", "admin")),
) -> PatientFileRead:
    """Soft-delete a file (dentist/admin). The bytes are retained; the row is just
    flagged archived and drops out of the default list. No hard DELETE."""
    record = db.get(PatientFile, file_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
        )

    record.archived = True
    record_audit(
        db,
        actor_id=staff.id,
        action="archive",
        entity="patient_file",
        entity_id=record.id,
    )
    db.commit()
    db.refresh(record)
    return PatientFileRead.model_validate(record)
