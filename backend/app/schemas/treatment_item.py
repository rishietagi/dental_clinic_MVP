"""Treatment-item request/response schemas.

Prices are `Decimal` throughout — never `float`. Pydantic validates the scale so
a price can't sneak in with more precision than the Numeric(10,2) column holds.

There is no `active` field on create/update: activation is its own pair of
endpoints (the patient archive/unarchive pattern), so "rename this item" and
"retire this item" are separate, auditable actions.

`kind` (6.7) is settable on create but **deliberately absent from update** — see
`TreatmentItemUpdate`.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Mirrors `models.treatment_item.ITEM_KINDS` and the DB CHECK. An unknown kind
# is a 422 here, long before it reaches the constraint.
ItemKind = Literal["treatment", "medicine"]


class TreatmentItemCreate(BaseModel):
    """Body for adding an item to the catalogue."""

    name: str = Field(min_length=1, description="Item name, e.g. 'Cleaning'.")
    default_price: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Default price. Editable per invoice later.",
    )
    kind: ItemKind = Field(
        default="treatment",
        description="'treatment' (a dental procedure) or 'medicine'.",
    )


class TreatmentItemUpdate(BaseModel):
    """Body for a partial update (PATCH). Both fields optional.

    Omitted fields are left unchanged. `active` is deliberately absent — use the
    activate/deactivate endpoints.

    **`kind` is deliberately absent too.** Re-kinding a live item would silently
    move every past invoice line it priced from one report bucket to another,
    rewriting history that has already been billed. To reclassify something,
    retire it and add it under the right kind.
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
    kind: ItemKind
    default_price: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime


class TreatmentItemListResponse(BaseModel):
    """A page of the catalogue plus the total count."""

    items: list[TreatmentItemRead]
    total: int
