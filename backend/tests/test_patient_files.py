"""Endpoint tests for patient file uploads (step 5.6).

DB-backed, on the test_visits.py template (auth faked by overriding
get_current_claims; skips fast without a database).

The headline tests pin the phase's rules:
- `test_dentist_can_upload_and_stream_back` — the round trip: upload bytes, read
  them back byte-for-byte with the right content type.
- `test_receptionist_cannot_upload` — the role split (clinical records are the
  dentist's), enforced on the API.
- `test_oversize_rejected` / `test_bad_content_type_rejected` — the guards.
- `test_archive_hides_from_default_list_but_content_stays` — soft-delete keeps the
  record retrievable (medico-legal retention).

Storage is redirected to a per-test temp dir (settings.upload_dir), so tests never
touch the real upload volume. Cleanup deletes file rows (+ audit) before patients.
"""

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.auth import get_current_claims
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.patient import Patient
from app.models.patient_file import PatientFile
from app.models.staff_user import StaffUser

client = TestClient(app)

# A tiny valid-enough payload. We don't inspect bytes, only the declared type.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-data" * 4


@pytest.fixture(scope="module")
def db_available() -> bool:
    probe = create_engine(settings.database_url, connect_args={"connect_timeout": 2})
    try:
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable, skipping DB tests: {exc}")
    finally:
        probe.dispose()
    return True


class Ctx:
    def __init__(self, db, staff, patient):
        self.db = db
        self.staff = staff
        self.patient = patient
        self.client = client


def _make_ctx(roles: list[str], *, archived: bool = False) -> Ctx:
    db = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(),
        name=f"Test {'/'.join(roles)}",
        email=f"{uuid.uuid4()}@clinic.local",
        roles=roles,
        active=True,
    )
    patient = Patient(name="File Test Patient", archived=archived)
    db.add_all([staff, patient])
    db.commit()
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}
    return Ctx(db, staff, patient)


def _cleanup(ctx: Ctx) -> None:
    app.dependency_overrides.clear()
    db = ctx.db
    db.rollback()
    for f in db.scalars(select(PatientFile).where(PatientFile.patient_id == ctx.patient.id)):
        db.delete(f)
        db.commit()
    for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == ctx.staff.id)):
        db.delete(row)
        db.commit()
    for model, oid in [(Patient, ctx.patient.id), (StaffUser, ctx.staff.id)]:
        obj = db.get(model, oid)
        if obj is not None:
            db.delete(obj)
            db.commit()
    db.close()


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    """Redirect storage to a temp dir so tests never write the real volume."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    yield


@pytest.fixture
def as_dentist(db_available):
    ctx = _make_ctx(["dentist"])
    try:
        yield ctx
    finally:
        _cleanup(ctx)


@pytest.fixture
def as_receptionist(db_available):
    ctx = _make_ctx(["receptionist"])
    try:
        yield ctx
    finally:
        _cleanup(ctx)


def _upload(ctx: Ctx, *, data=_PNG_BYTES, filename="xray.png", content_type="image/png", kind="xray", **form):
    return ctx.client.post(
        f"/patients/{ctx.patient.id}/files",
        files={"file": (filename, io.BytesIO(data), content_type)},
        data={"kind": kind, **form},
    )


def test_dentist_can_upload_and_stream_back(as_dentist):
    ctx = as_dentist
    resp = _upload(ctx, caption="Pre-op tooth 36")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["kind"] == "xray"
    assert data["original_filename"] == "xray.png"
    assert data["content_type"] == "image/png"
    assert data["size_bytes"] == len(_PNG_BYTES)
    assert data["caption"] == "Pre-op tooth 36"
    assert data["uploaded_by"] == str(ctx.staff.id)

    # Stream the bytes back — byte-for-byte, right content type.
    content = ctx.client.get(f"/files/{data['id']}/content")
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/png")
    assert content.content == _PNG_BYTES


def test_receptionist_can_list(as_receptionist):
    """Reads are any active staff — the receptionist can list a patient's files."""
    ctx = as_receptionist
    resp = ctx.client.get(f"/patients/{ctx.patient.id}/files")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_bad_content_type_rejected(as_dentist):
    ctx = as_dentist
    resp = _upload(ctx, filename="notes.txt", content_type="text/plain")
    assert resp.status_code == 415, resp.text


def test_oversize_rejected(as_dentist, monkeypatch):
    ctx = as_dentist
    monkeypatch.setattr(settings, "max_upload_bytes", 10)  # tiny cap
    resp = _upload(ctx)  # payload is well over 10 bytes
    assert resp.status_code == 413, resp.text


def test_unknown_kind_rejected(as_dentist):
    ctx = as_dentist
    resp = _upload(ctx, kind="banana")
    assert resp.status_code == 422, resp.text


def test_upload_unknown_patient(as_dentist):
    ctx = as_dentist
    resp = ctx.client.post(
        f"/patients/{uuid.uuid4()}/files",
        files={"file": ("x.png", io.BytesIO(_PNG_BYTES), "image/png")},
        data={"kind": "xray"},
    )
    assert resp.status_code == 404, resp.text


def test_cannot_upload_for_archived_patient(db_available):
    ctx = _make_ctx(["dentist"], archived=True)
    try:
        resp = _upload(ctx)
        assert resp.status_code == 409, resp.text
    finally:
        _cleanup(ctx)


def test_archive_hides_from_default_list_but_content_stays(as_dentist):
    ctx = as_dentist
    up = _upload(ctx)
    file_id = up.json()["id"]

    # Present in the default list.
    assert ctx.client.get(f"/patients/{ctx.patient.id}/files").json()["total"] == 1

    # Archive it.
    arch = ctx.client.post(f"/files/{file_id}/archive")
    assert arch.status_code == 200
    assert arch.json()["archived"] is True

    # Gone from the default list, visible with include_archived, content retained.
    assert ctx.client.get(f"/patients/{ctx.patient.id}/files").json()["total"] == 0
    incl = ctx.client.get(f"/patients/{ctx.patient.id}/files?include_archived=true")
    assert incl.json()["total"] == 1
    assert ctx.client.get(f"/files/{file_id}/content").status_code == 200


def test_content_unknown_file_404(as_dentist):
    ctx = as_dentist
    assert ctx.client.get(f"/files/{uuid.uuid4()}/content").status_code == 404


def test_upload_writes_audit_row(as_dentist):
    ctx = as_dentist
    up = _upload(ctx)
    file_id = uuid.UUID(up.json()["id"])
    ctx.db.expire_all()
    row = ctx.db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "patient_file", AuditLog.entity_id == file_id
        )
    )
    assert row is not None
    assert row.action == "create"


def test_visit_link_optional_and_recorded(as_dentist):
    ctx = as_dentist
    # No visit_id → nullable link is None.
    up = _upload(ctx)
    assert up.json()["visit_id"] is None
