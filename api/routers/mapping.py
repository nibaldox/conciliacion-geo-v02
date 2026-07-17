"""
Column-mapping router — schema-agnostic CSV/Excel ingestion.

Wraps ``core/column_mapping.py`` behind two thin HTTP endpoints used by
the React upload wizard:

    GET  /api/v1/mapping/schema      → canonical field schema (20 fields).
    POST /api/v1/mapping/detect      → auto-detect mapping from source
                                       column names, returning per-field
                                       confidence and the list of missing
                                       required fields.

These endpoints are stateless (no session DB write) so they remain cheap
and idempotent. The actual persistence of the mapping onto a real
uploaded file happens later in the upload pipeline (``apply_mapping`` in
``core/column_mapping.py``); this router is read-only metadata that helps
the user preview / override the auto-suggestions before confirming.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from core.column_mapping import (
    REQUIRED_FIELDS,
    auto_map,
    get_field_schema,
)


router = APIRouter(prefix="/mapping", tags=["mapping"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ColumnDetectRequest(BaseModel):
    """Body of POST /mapping/detect.

    ``columns`` is the raw, ordered list of source column names from the
    user's CSV/Excel header. Order matters for stable previewing but is
    not used by the auto-mapper (which deduplicates internally).
    """

    columns: List[str] = Field(
        default_factory=list,
        description="Ordered list of source column names from the uploaded file.",
    )


class ColumnDetectResponse(BaseModel):
    """Response of POST /mapping/detect.

    ``mapping`` maps each canonical field name → chosen source column,
    or ``None`` if the auto-mapper could not resolve it. ``confidence``
    gives, per canonical field, a tuple of (kind, score) where ``kind``
    is one of ``"exact"``, ``"fuzzy"``, or ``"unmatched"`` and ``score``
    is in [0.0, 1.0]. ``schema`` echoes the canonical field list so the
    UI can render labels / units / required flags without a second round
    trip to GET /mapping/schema.
    """

    mapping: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Canonical field name → selected source column (or null).",
    )
    confidence: Dict[str, Dict[str, object]] = Field(
        default_factory=dict,
        description=(
            "Per-field resolution metadata: "
            "{canonical: {kind: 'exact'|'fuzzy'|'unmatched', score: float}}."
        ),
    )
    field_schema: List[Dict[str, object]] = Field(
        default_factory=list,
        description="Canonical field schema (same as GET /mapping/schema). Renamed from 'schema' to avoid shadowing BaseModel.schema().",
        alias="schema",
    )
    is_complete: bool = Field(
        False,
        description="True iff every REQUIRED_FIELDS entry has a non-null mapping.",
    )
    missing_required: List[str] = Field(
        default_factory=list,
        description="Canonical field names in REQUIRED_FIELDS that are still unmapped.",
    )

    model_config = ConfigDict(populate_by_name=True)


class ColumnSchemaResponse(BaseModel):
    """Response of GET /mapping/schema — wraps ``get_field_schema()`` with
    an explicit ``required_fields`` list so the UI can validate before
    the user clicks Confirm.
    """

    fields: List[Dict[str, object]] = Field(
        default_factory=list,
        description="Canonical fields with name/required/description/unit/aliases/dtype.",
    )
    required_fields: List[str] = Field(
        default_factory=list,
        description="Subset of field names that the upload requires.",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/schema", response_model=ColumnSchemaResponse)
def mapping_schema():
    """Return the canonical blast-hole field schema.

    The schema is a single source of truth from ``core.column_mapping``
    (which itself derives field aliases from
    ``core.calculo_tronadura._CANONICAL_COLUMN_ALIASES``). The response
    is cheap to fetch and cached aggressively by the React client.
    """
    return ColumnSchemaResponse(
        fields=get_field_schema(),
        required_fields=list(REQUIRED_FIELDS),
    )


@router.post("/detect", response_model=ColumnDetectResponse)
def mapping_detect(body: ColumnDetectRequest):
    """Auto-detect a column mapping for the supplied source columns.

    The auto-mapper runs a two-pass strategy (exact normalized match,
    then fuzzy match with a 0.80 threshold) and tags each resolved
    canonical field with its confidence. Fields that still have a null
    mapping after both passes are listed in ``missing_required`` so the
    UI can show inline warnings and disable the Confirm button until all
    required fields are covered.
    """
    result = auto_map(body.columns)

    # MappingResult.confidence stores tuples ("exact"|"fuzzy"|"unmatched", float).
    # Pydantic does not serialize tuples natively in the schema above, so we
    # flatten them into {"kind": ..., "score": ...} dicts that are friendlier
    # to the TS client as well.
    confidence_flat: Dict[str, Dict[str, object]] = {}
    for canonical, (kind, score) in result.confidence.items():
        confidence_flat[canonical] = {"kind": kind, "score": score}

    return ColumnDetectResponse(
        mapping=dict(result.mapping),
        confidence=confidence_flat,
        field_schema=get_field_schema(),
        is_complete=result.is_complete,
        missing_required=list(result.missing_required),
    )
