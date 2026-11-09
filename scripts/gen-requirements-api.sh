#!/usr/bin/env bash
# scripts/gen-requirements-api.sh — regenera requirements-api.txt desde pyproject.toml + uv.lock.
# Exporta las dependencias no-dev del lock (uv export) y elimina los paquetes de la UI
# Streamlit (streamlit, plotly, altair, pydeck) con las mismas reglas con que siempre se filtró.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TMP_IN="$(mktemp)"
TMP_OUT="$(mktemp)"
trap 'rm -f "$TMP_IN" "$TMP_OUT"' EXIT

uv export --no-dev --no-emit-project --format requirements-txt --no-hashes > "$TMP_IN"

python3 - "$TMP_IN" > "$TMP_OUT" <<'PYEOF'
import re
import sys

HEADER = """\
# requirements-api.txt — entorno API (generado desde pyproject.toml + uv.lock)
# Fuente canónica: pyproject.toml + uv.lock (uv sync --frozen). Este archivo
# excluye la UI Streamlit/Plotly. NO editar a mano: regenerar con uv export.
"""

UI_PACKAGES = {"streamlit", "plotly", "altair", "pydeck"}
PKG_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==")
VIA_RE = re.compile(r"^    # via ([A-Za-z0-9_.\-]+)$")


def normalize(name: str) -> str:
    return name.lower().replace("_", "-")


with open(sys.argv[1], encoding="utf-8") as f:
    exported = f.read().splitlines()

out = list(HEADER.splitlines())
for line in exported:
    m = PKG_RE.match(line)
    if m and normalize(m.group(1)) in UI_PACKAGES:
        continue
    m = VIA_RE.match(line)
    if m and normalize(m.group(1)) in UI_PACKAGES:
        continue
    out.append(line)

sys.stdout.write("\n".join(out) + "\n")
PYEOF

mv "$TMP_OUT" requirements-api.txt
echo "requirements-api.txt regenerated ($(grep -c '==' requirements-api.txt) pinned packages)"
