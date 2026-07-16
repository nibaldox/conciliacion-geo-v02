"""Pure Excel workbook generation for export."""
import os
import tempfile
from typing import Any, Optional

from core import export_results


def build_workbook(
    comparison_results: list,
    params_design: list,
    params_topo: list,
    tolerances: dict,
    project_info: dict,
    df_pozos: Optional[Any] = None,
    sections: Optional[list] = None,
) -> bytes:
    """Generate a reconciliación Excel workbook and return its bytes."""
    output_path = os.path.join(tempfile.gettempdir(), "Conciliacion_Resultados.xlsx")
    export_results(
        comparison_results,
        params_design,
        params_topo,
        tolerances,
        output_path,
        project_info,
        df_pozos=df_pozos,
        sections=sections,
    )
    with open(output_path, "rb") as f:
        return f.read()
