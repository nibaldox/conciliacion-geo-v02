import io

from openpyxl import Workbook

from api.blast_import import mapping_errors, preview_payload, read_blast_file


def test_read_xlsx_selects_requested_sheet_and_lists_sheets():
    workbook = Workbook()
    first = workbook.active
    first.title = "resumen"
    first.append(["nota"])
    holes = workbook.create_sheet("pozos")
    holes.append(["Easting", "Northing"])
    holes.append([100, 200])
    buffer = io.BytesIO()
    workbook.save(buffer)

    frame, headers, sheets, encoding = read_blast_file(buffer.getvalue(), "holes.xlsx", "pozos")

    assert headers == ["Easting", "Northing"]
    assert sheets == ["resumen", "pozos"]
    assert frame.iloc[0].tolist() == [100, 200]
    assert encoding is None


def test_mapping_validation_rejects_unknown_duplicate_and_missing_columns():
    errors = mapping_errors(
        {"X": "East", "Y": "East", "Incl": "dip", "Az": "az", "Len": "length", "Z_collar": "z", "extra": "foo"},
        ["East", "dip", "az", "length", "z"],
    )

    assert any("desconocido" in error for error in errors)
    assert any("más de un campo" in error for error in errors)


def test_empty_optional_mapping_is_unassigned_and_design_surface_allows_missing_z():
    mapping = {"X": "East", "Y": "North", "Incl": "dip", "Az": "az", "Len": "length", "Z_collar": ""}

    assert mapping_errors(mapping, ["East", "North", "dip", "az", "length"], allow_missing_z=True) == []
    assert mapping_errors(mapping, ["East", "North", "dip", "az", "length"])


def test_csv_uses_legacy_encoding_fallback():
    frame, headers, sheets, encoding = read_blast_file("pozo,cota\n1,100\n".encode("cp1252"), "holes.csv")

    assert headers == ["pozo", "cota"]
    assert len(frame) == 1
    assert sheets == []
    assert encoding == "utf-8-sig"


def test_preview_is_limited_to_twenty_rows():
    frame, headers, sheets, encoding = read_blast_file(
        ("x\n" + "\n".join(str(value) for value in range(30))).encode(), "holes.csv", preview=True
    )
    payload = preview_payload(frame, headers, sheets, None, encoding)

    assert len(payload["preview"]) == 20
