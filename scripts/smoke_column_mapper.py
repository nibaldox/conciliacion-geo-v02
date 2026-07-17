"""Drop-in smoke test matching the task command:

    .venv/bin/python scripts/smoke_column_mapper.py

Equiv. to:
    .venv/bin/python -c "from ui.modulo_tronadura.column_mapper import render_column_mapper; print('OK')"
"""
from ui.modulo_tronadura.column_mapper import render_column_mapper
print("OK", render_column_mapper.__name__)
