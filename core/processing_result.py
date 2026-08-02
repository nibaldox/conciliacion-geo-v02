"""Canonical structured processing result — single source of truth.

Integración §5.7 — the processor returns ONE typed object so that the
router, persistence, API, UI and export all consume identical semantics.
``accepted_rows`` and ``rejected_rows`` are born here, never rebuilt by
downstream layers.

The summary distinguishes source rows from error records so a single
source row with three errors reports:

    rows_received          = 1
    rows_accepted          = 0
    rejected_source_rows   = 1   (unique source_row_index values)
    rejection_records      = 3   (total error records)

``rows_rejected`` is kept as a deprecated alias of ``rejected_source_rows``
for backward compatibility with older consumers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ProcessingResult:
    """Canonical structured result emitted by ``procesar_pozos``.

    Every downstream layer (API, persistence, UI, export) consumes this
    object — they do NOT redefine the semantics of accepted/rejected
    rows. The ``accepted_rows`` list contains plain dicts already
    serializable to JSON / Excel / SQLite JSON columns.
    """

    geometry_configuration: dict[str, Any] = field(default_factory=dict)
    accepted_rows: list[dict[str, Any]] = field(default_factory=list)
    rejected_rows: list[dict[str, Any]] = field(default_factory=list)
    event_warnings: list[dict[str, Any]] = field(default_factory=list)
    blocking_errors: list[dict[str, Any]] = field(default_factory=list)
    spatial_diagnostics: dict[str, Any] = field(default_factory=dict)
    rows_received: int = 0
    rows_accepted: int = 0
    rejected_source_rows: int = 0
    rejection_records: int = 0
    accepted_dataframe: Optional[Any] = None  # pandas DataFrame kept for back-compat
    scatter_lines: tuple = ((), (), ())  # (x_lines, y_lines, z_lines)

    def processing_summary(self) -> dict[str, Any]:
        """Stable summary with explicit, non-overlapping counts.

        ``rows_rejected`` is kept as a deprecated alias of
        ``rejected_source_rows``. ``rejection_records`` is the total
        number of (row × error) records emitted.
        """
        return {
            "rows_received": self.rows_received,
            "rows_accepted": self.rows_accepted,
            "rejected_source_rows": self.rejected_source_rows,
            "rejection_records": self.rejection_records,
            "rows_rejected": self.rejected_source_rows,  # deprecated alias
            "blocking_error_records": len(self.blocking_errors),
            "warning_records": len(self.event_warnings),
            "geometry_configuration_version": (
                self.geometry_configuration.get("geometry_configuration_version")
            ),
        }

    def to_dict(self, *, include_dataframe: bool = False) -> dict[str, Any]:
        """JSON-serializable view (the DataFrame is dropped by default)."""
        out = {
            "geometry_configuration": self.geometry_configuration,
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "event_warnings": self.event_warnings,
            "blocking_errors": self.blocking_errors,
            "processing_summary": self.processing_summary(),
            "spatial_diagnostics": self.spatial_diagnostics,
        }
        if include_dataframe:
            out["accepted_dataframe"] = self.accepted_dataframe
        return out

    @classmethod
    def from_rejections(
        cls,
        *,
        accepted_dataframe: Any,
        accepted_rows: list[dict[str, Any]],
        rejected_rows: list[dict[str, Any]],
        event_warnings: list[dict[str, Any]],
        spatial_diagnostics: dict[str, Any],
        geometry_configuration: dict[str, Any],
        rows_received: int,
        scatter_lines: tuple,
    ) -> "ProcessingResult":
        """Build a result computing the formal counts from the rejected list.

        ``rejected_source_rows`` counts UNIQUE source_row_index values
        (a row with three errors still counts as ONE rejected source row).
        ``rejection_records`` counts the total number of error records.
        """
        unique_rows: set = set()
        for r in rejected_rows:
            idx = r.get("source_row_index")
            unique_rows.add(idx)
        rejected_source_rows = len(unique_rows)
        return cls(
            geometry_configuration=geometry_configuration,
            accepted_rows=accepted_rows,
            rejected_rows=rejected_rows,
            event_warnings=event_warnings,
            blocking_errors=[] if accepted_rows else [
                {
                    "error_code": "NO_ACCEPTED_ROWS",
                    "message": "Ninguna fila pasó la validación geométrica.",
                    "recommended_action": "Corrija los datos de origen o la configuración y reprocese.",
                }
            ],
            spatial_diagnostics=spatial_diagnostics,
            rows_received=rows_received,
            rows_accepted=len(accepted_rows),
            rejected_source_rows=rejected_source_rows,
            rejection_records=len(rejected_rows),
            accepted_dataframe=accepted_dataframe,
            scatter_lines=scatter_lines,
        )
