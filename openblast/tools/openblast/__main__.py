"""CLI entry point for the openblast tool. Run as `python -m openblast`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from openblast import (
    Format,
    detect_format,
    get_version,
    load,
    validate,
    write_csv,
    convert_from_enaex,
)


def cmd_validate(args: argparse.Namespace) -> int:
    rows = load(args.path)
    result = validate(rows)
    print(f"Loaded {result.n_rows} rows from {args.path}")
    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for w in result.warnings[:20]:
            print(f"  - {w}")
        if len(result.warnings) > 20:
            print(f"  ... and {len(result.warnings) - 20} more")
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for e in result.errors[:20]:
            print(f"  - {e}")
        if len(result.errors) > 20:
            print(f"  ... and {len(result.errors) - 20} more")
        print(f"\nVALIDATION FAILED")
        return 1
    print("\nVALIDATION PASSED")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    src_format = args.source
    if src_format == "auto":
        src_format = detect_format(args.input).value
    if src_format == Format.ENAEX.value:
        rows = convert_from_enaex(args.input)
    else:
        print(f"Conversion from '{src_format}' not implemented yet. "
              f"Currently supported: enaex, openblast (passthrough).")
        if src_format == Format.OPENBLAST.value:
            rows = load(args.input)
        else:
            return 2
    write_csv(rows, args.output)
    print(f"Wrote {len(rows)} rows to {args.output}")
    result = validate(rows)
    if result.valid:
        print("Output validates against OpenBlast v1.0 schema.")
        return 0
    print(f"Output has {len(result.errors)} validation errors. Run openblast-validate for details.")
    return 1


def cmd_detect(args: argparse.Namespace) -> int:
    fmt = detect_format(args.path)
    print(f"{args.path}: {fmt.value}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    fmt = detect_format(args.path)
    print(f"Format: {fmt.value}")
    print(f"OpenBlast version: {get_version()}")
    if fmt == Format.OPENBLAST:
        rows = load(args.path)
        result = validate(rows)
        print(f"Rows: {result.n_rows}")
        print(f"Valid: {result.valid}")
        print(f"Errors: {len(result.errors)}, Warnings: {len(result.warnings)}")
        if rows:
            sample = rows[0]
            print(f"\nSample row (hole_id={sample.get('hole_id')}):")
            for k, v in sample.items():
                print(f"  {k}: {v}")
    else:
        print(f"\nFile is not OpenBlast native. Use `openblast convert --source {fmt.value}` "
              f"to convert before inspection.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="openblast",
        description=f"OpenBlast v{get_version()} — vendor-neutral CSV format for drill & blast data.",
    )
    parser.add_argument("--version", action="version", version=f"openblast {get_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Validate a CSV against the OpenBlast schema")
    p_validate.add_argument("path", help="Path to the CSV file to validate")
    p_validate.set_defaults(func=cmd_validate)

    p_convert = sub.add_parser("convert", help="Convert a vendor-format file to OpenBlast CSV")
    p_convert.add_argument("--input", required=True, help="Path to input file (.xlsx or .csv)")
    p_convert.add_argument("--source", choices=["auto", "enaex", "openblast"], default="auto",
                           help="Source format (default: auto-detect)")
    p_convert.add_argument("--output", required=True, help="Path to output OpenBlast CSV")
    p_convert.set_defaults(func=cmd_convert)

    p_detect = sub.add_parser("detect", help="Detect the format of a CSV file")
    p_detect.add_argument("path", help="Path to the CSV file")
    p_detect.set_defaults(func=cmd_detect)

    p_inspect = sub.add_parser("inspect", help="Inspect a file: format, validation, sample row")
    p_inspect.add_argument("path", help="Path to the CSV file")
    p_inspect.set_defaults(func=cmd_inspect)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())