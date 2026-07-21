"""The patient_file model — an uploaded X-ray, photo, or document (step 5.6).

Makes the app a real clinical record: a dentist attaches a radiograph, an
intraoral photo, or a scanned referral to a patient. This is **opaque file
storage** — we keep metadata and a storage key, and stream the bytes back on
request. It is NOT dental charting / an odontogram (drawing on teeth), which is
out of scope; we never interpret the image.

Storage split: the **bytes live on disk** (a Docker volume in dev, swappable for
Supabase Storage / S3 in Phase 7 by config), never in Postgres. This row holds
only metadata + `storage_key` (the opaque path the storage service uses to fetch
the bytes back). Keeping blobs out of the DB keeps backups/dumps small and the
storage backend replaceable.

FKs, and why each is nullable or not:
- `patient_id` -> `patient.id`, **NOT NULL**. A file always belongs to a patient.
  Indexed — the profile lists a patient's files.
- `visit_id` -> `visit.id`, **nullable**. Most files aren't visit-specific (a
  referral letter, a general photo); an X-ray taken during a sitting is. The
  optional link covers both without forcing a visit choice at upload time.
- `uploaded_by` -> `staff_user.id`, nullable (mirrors `visit.dentist_id`).

**Soft-delete via `archived`**, never hard-delete — medico-legal retention, the
same rule as `patient`. An archived file drops out of the default list but its
bytes stay fetchable by id, so historical records never break. No `ondelete` on
any FK (house style — nothing is hard-deleted).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class PatientFile(Base):
    __tablename__ = "patient_file"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Always belongs to a patient. Indexed — the profile lists by patient.
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )

    # Optional link to the sitting the file came from (e.g. this visit's X-ray).
    visit_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("visit.id"), nullable=True
    )

    # Who uploaded it. Nullable, mirroring visit.dentist_id.
    uploaded_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("staff_user.id"), nullable=True
    )

    # A coarse category (xray / photo / document). Free text — validated to a
    # small set in the API (a Literal), the app-level-enum pattern; no DB enum.
    kind: Mapped[str] = mapped_column(Text, nullable=False)

    # The user's filename, kept for display + download. NOT used as the storage
    # key (that's a generated UUID path — avoids traversal and collisions).
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)

    # MIME type, used to stream the bytes back with the right Content-Type and to
    # decide inline-preview vs download in the UI.
    content_type: Mapped[str] = mapped_column(Text, nullable=False)

    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Optional human note ("pre-op X-ray tooth 36").
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The opaque key the storage service uses to fetch the bytes. Never shown to
    # or supplied by the client.
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)

    # Soft-delete flag. NEVER hard-delete — medico-legal retention.
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<PatientFile {self.original_filename} patient={self.patient_id}{' [archived]' if self.archived else ''}>"
