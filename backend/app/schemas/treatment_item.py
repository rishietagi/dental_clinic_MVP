"""Treatment-item request/response schemas.

Prices are `Decimal` throughout — never `float`. Pydantic validates the scale so
a price can't sneak in with more precision than the Numeric(10,2) column holds.

There is no `active` field on create/update: activation is its own pair of
endpoints (the patient archive/unarchive pattern), so "rename this item" and
"retire this item" are separate, auditable actions.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TreatmentItemCreate(BaseModel):
    """Body for adding a treatment to the catalogue. Both fields required."""

    name: str = Field(min_length=1, description="Procedure name, e.g. 'Cleaning'.")
    default_price: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Default price. Editable per invoice later.",
    )


class TreatmentItemUpdate(BaseModel):
    """Body for a partial update (PATCH). Both optional.

    Omitted fields are left unchanged. `active` is deliberately absent — use the
    activate/deactivate endpoints.
    """

    name: str | None = Field(default=None, min_length=1)
    default_price: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )


class TreatmentItemRead(BaseModel):
    """Everything the API returns about one treatment item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    default_price: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime


class TreatmentItemListResponse(BaseModel):
    """A page of the catalogue plus the total count."""

    items: list[TreatmentItemRead]
    total: int
