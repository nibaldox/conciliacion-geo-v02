"""
Universal column mapping for blast-hole CSV/Excel ingestion.

This module decouples the blast-hole processing pipeline from any specific
data schema (ENAEX, O-Pit, custom). Instead of requiring the user's file
to have exact column names, we expose a canonical set of fields and let
the user (or auto-detection) map their source columns to them.

Flow:
    1. ``auto_map(source_columns)`` — fuzzy + alias matching, returns best
       guesses for each canonical field.
    2. ``validate_mapping(mapping)`` — checks all required fields are covered.
    3. ``apply_mapping(df, mapping)`` — renames + coerces types, returns a
       clean DataFrame ready for ``calculo_tronadura.process_blast_holes``.

The canonical schema is derived from ``calculo_tronadura._CANONICAL_COLUMN_ALIASES``
so there is a single source of truth for alias names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

import pandas as pd


# ─── Canonical schema (single source of truth) ─────────────────────────────

@dataclass(frozen=True)
class CanonicalField:
    name: str
    required: bool
    description: str
    unit: str
    aliases: tuple[str, ...]
    dtype: str = "float"  # "float" | "int" | "str"


CANONICAL_FIELDS: tuple[CanonicalField, ...] = (
    CanonicalField("X",              True,  "Coordenada Este",            "m",  ("Latitud_Geo", "Easting", "X", "Este", "East", "X_collar")),
    CanonicalField("Y",              True,  "Coordenada Norte",           "m",  ("Longitud_Geo", "Northing", "Y", "Norte", "North", "Y_collar")),
    CanonicalField("Z_collar",       True,  "Cota collar del pozo",       "m",  ("Nombre_Banco", "Banco", "Cota_Collar", "Z", "Elevation", "Collar_Elev", "Z_collar")),
    CanonicalField("Incl",           True,  "Inclinación desde vertical", "°",  ("Inclinacion_real", "Dip", "Inclinacion", "Inclination", "Incl", "Dip_deg", "Dip_Deg", "Incl_deg", "Pendiente")),
    CanonicalField("Az",             True,  "Azimut (desde Norte)",       "°",  ("Azimuth_real", "Heading", "Azimuth", "Azimut", "Az", "Bearing", "Heading_deg", "Azimuth_deg", "Direction", "Dir_Az")),
    CanonicalField("Len",            True,  "Longitud perforada",         "m",  ("longitud_real", "Length", "Profundidad", "Drill_Length", "Len", "Depth", "Hole_Length")),
    CanonicalField("Burden",         False, "Burden",                     "m",  ("Burden", "Burden_Real", "Burden_diseno", "B")),
    CanonicalField("Esp",            False, "Espaciamiento",              "m",  ("Espaciamiento", "Espaciamiento_Real", "Spacing", "S", "Esp")),
    CanonicalField("Diam_mm",        False, "Diámetro perforación",       "mm", ("Diametro", "Diametro_pozo", "Diameter", "D_mm", "Diam_mm")),
    CanonicalField("Tipo_Explosivo", False, "Tipo de explosivo",          "",   ("Tipo_Explosivo", "Explosivo", "Explosive_Type", "Nombre", "nombre")),
    CanonicalField("Taco_m",         False, "Taco (stemming)",            "m",  ("Taco", "Stemming", "stemming_real", "Taco_m")),
    CanonicalField("Secuencia",      False, "Secuencia de detonación",    "",   ("Secuencia", "Secuencia_Iniciacion", "Detonador_Nro", "Sequence")),
    CanonicalField("Retardo_ms",     False, "Retardo",                    "ms", ("Retardo_ms", "Delay_ms", "Tiempo_Retardo")),
    CanonicalField("Fila",           False, "Fila del pozo",              "",   ("Numero_Fila", "Fila_Pozo", "Row", "Fila")),
    CanonicalField("Carga_Fondo_kg",     False, "Carga de fondo",          "kg", ("Carga_Fondo_kg", "Kilos_Fondo", "Bottom_Charge")),
    CanonicalField("Carga_Columna_kg",   False, "Carga de columna",        "kg", ("Carga_Columna_kg", "Kilos_Columna", "Column_Charge")),
    CanonicalField("Longitud_Carga_m",   False, "Longitud cargada",        "m",  ("Longitud_Carga_m", "Charge_Length")),
    CanonicalField("Tipo_Pozo",      False, "Tipo de pozo",               "",   ("Tipo_Pozo", "Hole_Type")),
    CanonicalField("Az_Diseno",      False, "Azimut de diseño",           "°",  ("Azimuth_Diseno", "Design_Azimuth", "Az_Diseno")),
    CanonicalField("Incl_Diseno",    False, "Inclinación de diseño",      "°",  ("Inclinacion_Diseno", "Design_Dip", "Incl_Diseno")),
)

REQUIRED_FIELDS: tuple[str, ...] = tuple(f.name for f in CANONICAL_FIELDS if f.required)
OPTIONAL_FIELDS: tuple[str, ...] = tuple(f.name for f in CANONICAL_FIELDS if not f.required)
_ALL_ALIASES: dict[str, tuple[str, ...]] = {f.name: f.aliases for f in CANONICAL_FIELDS}


# ─── Pure functions ─────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Normalize a column name for comparison: lowercase, strip, collapse spaces, remove accents."""
    out = s.lower().strip()
    # Collapse internal whitespace
    out = " ".join(out.split())
    # Remove common non-alphanumeric chars that vary between schemas
    for ch in "()-_./#":
        out = out.replace(ch, " ")
    return " ".join(out.split())


def _fuzzy_ratio(a: str, b: str) -> float:
    """Similarity ratio in [0, 1] using difflib SequenceMatcher."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _best_alias_match(
    source_col: str,
    aliases: Iterable[str],
    threshold: float = 0.80,
) -> str | None:
    """Return the best-matching alias for ``source_col`` above ``threshold``, or None."""
    best_alias: str | None = None
    best_score = 0.0
    for alias in aliases:
        # Exact (normalized) match is an instant winner
        if _normalize(source_col) == _normalize(alias):
            return alias
        score = _fuzzy_ratio(source_col, alias)
        if score > best_score:
            best_score = score
            best_alias = alias
    return best_alias if best_score >= threshold else None


@dataclass
class MappingResult:
    """Result of auto_map: the mapping plus metadata about how each was resolved."""
    mapping: dict[str, str | None]
    # For each canonical field: ("exact" | "fuzzy" | "unmatched", score)
    confidence: dict[str, tuple[str, float]] = field(default_factory=dict)

    @property
    def missing_required(self) -> list[str]:
        return [k for k in REQUIRED_FIELDS if self.mapping.get(k) is None]

    @property
    def is_complete(self) -> bool:
        return len(self.missing_required) == 0


def auto_map(source_columns: Iterable[str]) -> MappingResult:
    """
    Auto-detect the best mapping from source CSV columns to canonical fields.

    Uses a two-pass strategy:
      1. Exact (normalized) match against known aliases.
      2. Fuzzy match (difflib, threshold 0.80) for typos / variants.

    Each source column is assigned to at most one canonical field. If two
    canonical fields match the same source column, the one with the higher
    score wins and the other is left unmatched.

    Args:
        source_columns: the column names from the user's CSV/Excel.

    Returns:
        A ``MappingResult`` with the mapping and per-field confidence.
    """
    sources = list(dict.fromkeys(str(c) for c in source_columns))  # dedupe, preserve order
    mapping: dict[str, str | None] = {f.name: None for f in CANONICAL_FIELDS}
    confidence: dict[str, tuple[str, float]] = {}

    # Track which source columns have been claimed so we don't double-assign
    claimed: set[str] = set()

    # Pass 1: exact (normalized) matches
    for fdef in CANONICAL_FIELDS:
        for src in sources:
            if src in claimed:
                continue
            if any(_normalize(src) == _normalize(a) for a in fdef.aliases):
                mapping[fdef.name] = src
                confidence[fdef.name] = ("exact", 1.0)
                claimed.add(src)
                break

    # Pass 2: fuzzy matches for remaining unmatched fields
    for fdef in CANONICAL_FIELDS:
        if mapping[fdef.name] is not None:
            continue
        best_src: str | None = None
        best_score = 0.0
        for src in sources:
            if src in claimed:
                continue
            alias = _best_alias_match(src, fdef.aliases, threshold=0.80)
            if alias is not None:
                score = _fuzzy_ratio(src, alias)
                if score > best_score:
                    best_score = score
                    best_src = src
        if best_src is not None:
            mapping[fdef.name] = best_src
            confidence[fdef.name] = ("fuzzy", best_score)
            claimed.add(best_src)

    # Mark unmatched
    for fdef in CANONICAL_FIELDS:
        if mapping[fdef.name] is None:
            confidence[fdef.name] = ("unmatched", 0.0)

    return MappingResult(mapping=mapping, confidence=confidence)


def validate_mapping(mapping: dict[str, str | None]) -> list[str]:
    """
    Validate a user-confirmed mapping. Returns a list of error messages
    (empty = valid).

    Checks:
      - All required fields are mapped (not None).
      - No two canonical fields map to the same source column.
      - Source columns actually exist (no dangling references).
    """
    errors: list[str] = []

    # Required check
    missing = [k for k in REQUIRED_FIELDS if not mapping.get(k)]
    if missing:
        errors.append(f"Faltan campos requeridos: {', '.join(missing)}")

    # Duplicate target check
    seen_targets: dict[str, str] = {}
    for canonical, source in mapping.items():
        if source is None:
            continue
        if source in seen_targets:
            errors.append(
                f"'{source}' está asignado a dos campos: "
                f"'{seen_targets[source]}' y '{canonical}'"
            )
        else:
            seen_targets[source] = canonical

    return errors


def apply_mapping(
    df: pd.DataFrame,
    mapping: dict[str, str | None],
) -> pd.DataFrame:
    """
    Apply a validated column mapping to a DataFrame.

    Renames source columns to canonical names, coerces types, and drops
    rows where any required field is NaN.

    Raises ``ValueError`` if the mapping is invalid (call ``validate_mapping``
    first to get structured errors).
    """
    errors = validate_mapping(mapping)
    if errors:
        raise ValueError("; ".join(errors))

    rename_map: dict[str, str] = {}
    for canonical, source in mapping.items():
        if source is not None and source in df.columns:
            rename_map[source] = canonical

    df_out = df.rename(columns=rename_map).copy()

    # Type coercion based on canonical dtype
    for fdef in CANONICAL_FIELDS:
        col = fdef.name
        if col not in df_out.columns:
            continue
        if fdef.dtype == "float":
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce")
        elif fdef.dtype == "int":
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce").astype("Int64")  # type: ignore[union-attr]
        # str: leave as-is

    # Drop rows missing required fields
    required_present = [c for c in REQUIRED_FIELDS if c in df_out.columns]
    if required_present:
        df_out = df_out.dropna(subset=required_present)

    return df_out


def get_field_schema() -> list[dict[str, object]]:
    """
    Return the canonical schema as a list of plain dicts (for API / UI consumption).
    Each dict has: name, required, description, unit, aliases, dtype.
    """
    return [
        {
            "name": f.name,
            "required": f.required,
            "description": f.description,
            "unit": f.unit,
            "aliases": list(f.aliases),
            "dtype": f.dtype,
        }
        for f in CANONICAL_FIELDS
    ]
