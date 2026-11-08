import hashlib
import math
import numbers
import re
from typing import Any, Mapping, Sequence


def blast_data_status(settings: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from core.blast_hole_consolidation import BLAST_ALGORITHM_VERSION
    except ImportError:
        BLAST_ALGORITHM_VERSION = None
    version = settings.get("blast_algorithm_version")
    if not isinstance(version, str):
        version = None
    return {
        "data_status": "current" if BLAST_ALGORITHM_VERSION is not None and version == BLAST_ALGORITHM_VERSION else "legacy_reimport_required",
        "algorithm_version": version,
    }


def blast_hole_id(record: Mapping[str, Any], fallback: Any) -> str:
    for key in ("id_pozo", "hole_id", "label_pozo", "uniqid", "Hole_ID", "pozo"):
        value = record.get(key)
        if value is not None and not (isinstance(value, (float,)) and math.isnan(value)) and str(value) != "":
            return str(value)
    return str(fallback)


def _source_index_key(value: Any, ordinal: int) -> str:
    if value is None or (isinstance(value, (float,)) and math.isnan(value)):
        return f"ordinal:{ordinal}"
    if isinstance(value, numbers.Real) and float(value).is_integer():
        value = int(value)
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        value = int(value)
    return f"source:{value}"


def blast_row_ids(session_id: str, records: Sequence[Mapping[str, Any]]) -> list[str]:
    """Assign stable, unique row identities in original record order."""
    occurrences: dict[tuple[str, str], int] = {}
    row_ids = []
    for ordinal, record in enumerate(records):
        hole_id = blast_hole_id(record, ordinal)
        key = (_source_index_key(record.get("source_row_index"), ordinal), hole_id)
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        digest_input = f"{session_id}:{key[0]}:{hole_id}:{occurrence}"
        row_ids.append(hashlib.sha256(digest_input.encode()).hexdigest()[:24])
    return row_ids
