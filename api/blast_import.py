import io
import json
import csv
from pathlib import PurePath
from typing import Any

import pandas as pd

from core.column_mapping import CANONICAL_FIELDS, REQUIRED_FIELDS, auto_map


def _decode(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1"), "latin-1"


def read_blast_file(content: bytes, filename: str, sheet_name: str | None = None, preview: bool = False) -> tuple[pd.DataFrame, list[str], list[str], str | None]:
    suffix = PurePath(filename or "").suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        try:
            workbook = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
            sheets = list(workbook.sheet_names)
            selected = sheet_name or (sheets[0] if sheets else None)
            if selected not in sheets:
                raise ValueError("La hoja solicitada no existe.")
            frame = pd.read_excel(workbook, sheet_name=selected, engine="openpyxl", nrows=20 if preview else None)
            from openpyxl import load_workbook
            raw_book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            raw_headers = [str(value) if value is not None else "" for value in next(raw_book[selected].iter_rows(max_row=1, values_only=True), ())]
            raw_book.close()
            if len(raw_headers) != len(set(raw_headers)):
                raise ValueError("El archivo contiene encabezados duplicados.")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"XLSX inválido: {exc}") from exc
        return frame, [str(c) for c in frame.columns], sheets, None
    if suffix not in (".csv", ""):
        raise ValueError("Formato no admitido; use CSV o XLSX.")
    decoded, encoding = _decode(content)
    try:
        raw_headers = next(csv.reader(io.StringIO(decoded)), [])
        if len(raw_headers) != len(set(raw_headers)):
            raise ValueError("El archivo contiene encabezados duplicados.")
        frame = pd.read_csv(io.StringIO(decoded), engine="python", on_bad_lines="warn", nrows=20 if preview else None)
    except Exception as exc:
        raise ValueError(f"CSV inválido: {exc}") from exc
    return frame, [str(c) for c in frame.columns], [], encoding


def mapping_errors(mapping: Any, headers: list[str], *, allow_missing_z: bool = False) -> list[str]:
    if not isinstance(mapping, dict):
        return ["column_map debe ser un objeto JSON."]
    fields = {field.name for field in CANONICAL_FIELDS}
    errors = [f"Campo canónico desconocido: {key}" for key in mapping if key not in fields]
    targets = [value for value in mapping.values() if value not in (None, "")]
    if any(not isinstance(value, str) for value in targets):
        return errors + ["Cada asignación debe ser el nombre de una columna fuente."]
    if len(targets) != len(set(targets)):
        errors.append("Una columna fuente no puede asignarse a más de un campo.")
    required = [key for key in REQUIRED_FIELDS if not (allow_missing_z and key == "Z_collar")]
    errors.extend(f"Falta mapear el campo requerido {key}." for key in required if not mapping.get(key))
    errors.extend(f"La columna fuente no existe: {value}" for value in targets if value not in headers)
    return errors


def preview_payload(frame: pd.DataFrame, headers: list[str], sheets: list[str], sheet_name: str | None, encoding: str | None) -> dict[str, object]:
    suggestion = auto_map(headers)
    preview = frame.head(20).where(pd.notna(frame.head(20)), None)
    return {
        "file_type": "xlsx" if sheets else "csv",
        "encoding": encoding,
        "sheets": sheets,
        "sheet_name": sheet_name,
        "headers": headers[:1000],
        "preview": json.loads(preview.to_json(orient="records", date_format="iso")),
        "suggested_mapping": suggestion.mapping,
        "confidence": {key: {"kind": kind, "score": score} for key, (kind, score) in suggestion.confidence.items()},
        "missing_required": suggestion.missing_required,
    }
