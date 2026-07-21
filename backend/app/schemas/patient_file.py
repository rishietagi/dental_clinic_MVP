"""Patient-file response schemas (step 5.6).

Only metadata crosses the wire here — never the bytes. The bytes are streamed by a
separate content endpoint. The upload itself is a multipart form (file + fields),
so its "create" shape lives in the router as `UploadFile` + `Form(...)` params, not
as a Pydantic body — Pydantic doesn't model multipart uploads.

`kind` is the small set of categories the UI offers; validated as a Literal at the
router (unknown -> 422), the app-level-enum pattern, so no DB enum to migrate later.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# The categories a file can be tagged with. Kept in sync with the frontend picker.
FileKind = Literal["xray", "photo", "document"]


class PatientFileRead(BaseModel):
    """Everything the API returns about one file — metadata only, no bytes."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    visit_id: UUID | None
    uploaded_by: UUID | None
    kind: str
    original_filename: str
    content_type: str
    size_bytes: int
    caption: str | None
    archived: bool
    created_at: datetime


class PatientFileList(BaseModel):
    """A patient's files plus the total count."""

    items: list[PatientFileRead]
    total: int
