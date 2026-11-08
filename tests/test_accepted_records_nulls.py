import json

import numpy as np
import pandas as pd

from core.calculo_tronadura import _df_to_accepted_records


def test_accepted_records_preserve_missing_and_measured_zero():
    df = pd.DataFrame({"kg_per_meter": [np.nan, 0.0, np.inf], "altura_carga_m": [np.nan, 0.0, -np.inf], "other": [np.nan, 0.0, np.inf]})
    rows = _df_to_accepted_records(df)
    assert [(r["carga"], r["descarga"], r["other"]) for r in rows] == [(None, None, None), (0.0, 0.0, 0.0), (None, None, None)]
    json.dumps(rows, allow_nan=False)


def test_accepted_records_missing_derived_inputs_are_null():
    row = _df_to_accepted_records(pd.DataFrame({"Len": [10.0]}))[0]
    assert row["carga"] is None
    assert row["descarga"] is None
