"""Pydantic request/response schemas — the API's data contracts.

Kept separate from models (persistence) and routers (HTTP wiring). Using explicit
response models means only the fields we list are ever serialized — no accidental
column leakage.
"""
