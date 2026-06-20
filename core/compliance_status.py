"""Single source of truth for geotechnical compliance and feasibility strings.

Status literals previously appeared inline in several files
(param_extractor, blast_correlation, excel_writer, ai_service,
report_generator) and feasibility literals were duplicated in
blast_advisor. Consolidated here to avoid typo bugs and make grep easier.
"""
from __future__ import annotations


STATUS_CUMPLE = "CUMPLE"
STATUS_FUERA = "FUERA DE TOLERANCIA"
STATUS_NO_CUMPLE = "NO CUMPLE"
STATUS_NO_CONSTRUIDO = "NO CONSTRUIDO"
STATUS_FALTA_BANCO = "FALTA BANCO"
STATUS_EXTRA = "EXTRA"
STATUS_BANCO_ADICIONAL = "BANCO ADICIONAL"
STATUS_RAMPA_OK = "RAMPA OK"

ALL_STATUSES = frozenset({
    STATUS_CUMPLE, STATUS_FUERA, STATUS_NO_CUMPLE, STATUS_NO_CONSTRUIDO,
    STATUS_FALTA_BANCO, STATUS_EXTRA, STATUS_BANCO_ADICIONAL, STATUS_RAMPA_OK,
})

PASSING_STATUSES: frozenset = frozenset({STATUS_CUMPLE, STATUS_RAMPA_OK})


def is_passing_status(status: str) -> bool:
    """Return True when ``status`` represents a compliant outcome.

    Both an outright ``CUMPLE`` and a ramp that meets its geometry
    (``RAMPA OK``) count as passing. Comparison is direct (no
    substring matching) so partial labels are not misclassified.
    """
    return status in PASSING_STATUSES


FEASIBILITY_APPLICABLE = "APPLICABLE"
FEASIBILITY_CAUTION = "CAUTION"
FEASIBILITY_INFEASIBLE = "INFEASIBLE"
FEASIBILITY_INSUFFICIENT = "INSUFFICIENT_DATA"

ALL_FEASIBILITY = frozenset({
    FEASIBILITY_APPLICABLE,
    FEASIBILITY_CAUTION,
    FEASIBILITY_INFEASIBLE,
    FEASIBILITY_INSUFFICIENT,
})
