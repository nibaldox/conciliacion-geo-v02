# OpenBlast

> **Vendor-neutral CSV format for open-pit drill and blast hole data.**

OpenBlast is a simple, well-documented CSV format designed so that any mining operation — regardless of whether they use ENAEX, Datamine, MinePlan, Surpac, Vulcan, or an Excel spreadsheet — can share their drill and blast data with the `conciliacion-geo-v02` reconciliation tool (or any other OpenBlast-compliant consumer).

This directory contains the **v1.0.0** specification of OpenBlast.

## Why OpenBlast?

The `conciliacion-geo-v02` project was built around a specific ENAEX Excel schema. That worked for one mine (Zalívar, Chile) but blocks adoption by anyone using a different software stack. After surveying the existing landscape — Open Mining Format (binary, GMG), Datamine drillhole format (exploration-focused), GeoSciML/EarthResourceML (geology-only), Orica SHOTPlus (proprietary) — we concluded that **no open standard covers production blastholes**. OpenBlast fills that gap.

See `docs/../OPENBLAST_DESIGN.md` for the full design rationale.

## Quick start

### As a data producer

```bash
# 1. Download the schema
curl -O https://raw.githubusercontent.com/nibaldox/conciliacion-geo-v02/main/openblast/schema/openblast-1.0.0.schema.json

# 2. Edit the example
cp openblast/examples/minimal.csv my_holes.csv
$EDITOR my_holes.csv

# 3. Validate before upload
pip install openblast
openblast-validate my_holes.csv
```

### As a tool author

```python
import json
import jsonschema
import pandas as pd

with open("openblast/schema/openblast-1.0.0.schema.json") as f:
    schema = json.load(f)
row_schema = schema["items"]

df = pd.read_csv("my_holes.csv")
for _, row in df.iterrows():
    jsonschema.validate(row.to_dict(), row_schema)
print("All rows valid.")
```

### As an ENAEX user

```bash
openblast-convert --from enaex enaex_pozos_2026.xlsx --to openblast holes.csv
openblast-validate holes.csv
```

## Contents

```
openblast/
├── README.md                                       ← you are here
├── CHANGELOG.md                                    ← version history
├── VERSION                                         ← current: 1.0.0
├── LICENSE                                         ← Apache-2.0
├── schema/
│   ├── openblast-1.0.0.schema.json                 ← JSON Schema (Draft-07) for validation
│   └── openblast-1.0.0.table-schema.json           ← Frictionless Data Table Schema equivalent
├── examples/
│   ├── minimal.csv                                 ← 5 wells, only required fields
│   ├── complete.csv                                ← 5 wells, all fields
│   └── datapackage.json                            ← Frictionless metadata wrapper
├── mappings/
│   ├── enaex-to-openblast.csv                      ← ENAEX → OpenBlast field map
│   ├── datamine-to-openblast.csv                   ← Datamine/MinePlan collar/survey/assay → OpenBlast
│   └── surpac-to-openblast.csv                     ← Surpac drillhole DB → OpenBlast
├── docs/
│   ├── field-reference.md                          ← full table of every field, units, semantics
│   ├── versioning.md                               ← SemVer 2.0 policy for OpenBlast
│   └── migrations/
│       └── 1.0.0-initial.md                        ← initial release notes
└── tools/                                          ← CLI tooling (planned for v1.1)
```

## Schema at a glance

| Block | Required | Fields |
|---|---|---|
| A. Identification | ✅ | `hole_id`, `blast_id`, `sequence` |
| B. Location | ✅ | `easting`, `northing`, `elevation`, `dip`, `azimuth` |
| C. Geometry | ✅ | `hole_length_actual`, `diameter_mm`, `burden`, `spacing`, `hole_length_planned` (planned), `subdrill` (planned) |
| D. Charge | ✅ | `explosive_type`, `explosive_kg_actual`, `explosive_kg_planned`, `explosive_density_g_cc`, `emulsion_kg`, `anfo_kg`, `bulk_kg` |
| E. Stemming | ✅ | `stemming_length_m` |
| F. Metadata | ✅ | `mine_site`, `bench_id`, `shot_at`, `operator` |
| G. Optional |  | `rock_mass_rating`, `density_rock_t_m3`, `initiation_system`, `delay_ms`, `bottom_hole_x/y/z`, `decoupling_ratio`, `comment`, `anomaly_flag` |

17 fields are mandatory. The schema uses `additionalProperties: true` so vendor-specific columns (e.g. ENAEX `Nombre_Rajo`, Orica `BlastId`) are preserved when round-tripping through OpenBlast.

## Versioning

OpenBlast follows **Semantic Versioning 2.0.0**. See `docs/versioning.md` for the full policy.

Current: **1.0.0**. Compatible with v1.x readers.

## Contributing

Issues and PRs welcome. OpenBlast is part of the `conciliacion-geo-v02` project; please follow that project's contribution guidelines.

## License

Apache-2.0. See `LICENSE`.