# OpenBlast Field Reference

This document is the **authoritative reference** for every field defined in the OpenBlast v1.0 schema. For programmatic validation, see `schema/openblast-1.0.0.schema.json`.

## Conventions

- **Naming**: `snake_case`. No accents, no ñ.
- **Units**: SI (metres, kilograms, seconds, degrees). Exceptions documented per field.
- **Coordinates**: Planar X/Y and elevation Z. CRS declared externally in `datapackage.json` `crs` field.
- **Required fields** must be present and non-null. Optional fields may be absent or null.
- **Enums** are case-sensitive. Match exactly.

## Block A — Identification (mandatory)

### `hole_id` (string, required)
Unique hole identifier within the dataset. Equivalent to `BHID` in Datamine/MinePlan, `Nombre` in ENAEX, `HOLE_ID` in acQuire.

Examples:
- `ZH-1423-A`
- `F8_2930_07-33_03ENE` (ENAEX-style with date)
- `POLV-2026-04-12-001`

### `blast_id` (string, required)
Identifier of the blast/polygon this hole belongs to. Allows grouping holes for powder factor, vibration, and fragmentation analyses. ENAEX does not have a single blast_id column; it is typically derived from `Nombre_Rajo + fecha_tronadura`.

Examples:
- `POLV-2026-04-12-A`
- `ZALIVAR_F8_2930_07-33`

### `sequence` (integer, required)
Initiation sequence row. Holes with the same sequence fire simultaneously. Starts at 1 (sequence 0 reserved for pre-split / cushion holes that fire first).

## Block B — Location (mandatory)

### `easting` (number, required)
Easting coordinate of the collar in metres. CRS declared in `datapackage.json`. ENAEX calls this `Longitud_Geo` (a confusing naming choice inherited from some legacy GIS systems).

### `northing` (number, required)
Northing coordinate in metres. ENAEX calls this `Latitud_Geo`.

### `elevation` (number, required)
Collar elevation in metres. ENAEX reports `Z_collar` after a +15 m bench offset; OpenBlast stores the raw elevation (collar altitude).

### `dip` (number, required, range -90 to 90)
Hole dip angle in degrees. Convention: positive downward (0 = vertical, 90 = horizontal). Negative values indicate up-holes.

Examples: `-65.0`, `-90.0`, `0.0` (vertical), `15.0` (slightly up).

### `azimuth` (number, required, range 0-360)
Hole azimuth in degrees clockwise from North. 0=N, 90=E, 180=S, 270=W. ENAEX uses `Azimuth_real`.

## Block C — Geometry (mandatory)

### `hole_length_actual` (number, required)
Actual drilled length in metres. ENAEX `longitud_real`. Datamine `LENGTH` (single column used for both planned and actual).

### `diameter_mm` (number, required)
Bit diameter in millimetres. ENAEX stores this in `diametro` (mm) and `diametro_pulgada` (inches; ×25.4 to convert). Common values: 270 mm (10⅝"), 311 mm (12¼"), 165 mm (6½" for presplit).

### `burden` (number, required)
Burden in metres — distance to the nearest free face at the moment of charging. ENAEX does not include this; it is typically computed from neighbouring hole coordinates.

### `spacing` (number, required)
Spacing in metres — distance to the nearest neighbouring hole in the same row. ENAEX does not include this; compute from neighbours.

### `hole_length_planned` (number, optional)
Planned drilled length in metres. ENAEX `Longitud_teo`. Recommended (the difference between planned and actual tells you about drilling deviations).

### `subdrill` (number, optional)
Subdrilling / pasadura in metres. Length drilled below the planned toe to ensure the floor breaks cleanly. Typically 0.5-1.5 m.

## Block D — Charge (mandatory)

### `explosive_type` (string, required, enum)
Main explosive category. Allowed values:
- `ANFO` — ammonium nitrate + fuel oil
- `Heavy ANFO` — ANFO/emulsion blend (ENAEX: Pirex series)
- `Emulsion` — water-based emulsion (ENAEX: Enaline)
- `Bulk emulsion` — pump-loaded emulsion
- `ANFO + Emulsion` — both products loaded in same hole (common with bulk trucks)
- `Other` — anything not covered above

### `explosive_kg_actual` (number, required)
Actual kg of explosive loaded into the hole. ENAEX `Kilos_Cargados_real`. **The single most important field for powder factor calculations.**

### `explosive_kg_planned` (number, optional)
Planned kg of explosive per design (theoretical).

### `explosive_density_g_cc` (number, optional, range 0-2)
In-situ explosive density in g/cm³. Typical values:
- ANFO: 0.80
- Emulsion: 1.15-1.25
- Heavy ANFO: 1.00-1.20

### `emulsion_kg`, `anfo_kg`, `bulk_kg` (numbers, optional)
Breakdown by product if the hole has mixed loads. Sum should equal `explosive_kg_actual`.

## Block E — Stemming (mandatory)

### `stemming_length_m` (number, required)
Stemming (taco) length in metres at the top of the hole. ENAEX `stemming_real`. Typical 4-8 m depending on hole diameter.

## Block F — Metadata (mandatory)

### `mine_site` (string, required)
Mine site / pit identifier. ENAEX `Nombre_Rajo` (constant within a dataset).

### `bench_id` (string, required)
Bench identifier. ENAEX `Nombre_Banco`. Common formats: numeric (`2930`), or prefixed (`B-2930`).

### `shot_at` (string, required, ISO-8601 date-time)
Timestamp of detonation with explicit UTC offset. Format: `YYYY-MM-DDTHH:MM:SS±HH:MM`.

Examples:
- `2026-04-12T13:42:00-03:00` (Chile summer time)
- `2026-04-12T16:42:00+00:00` (UTC)
- `2026-04-12T09:42:00-07:00` (Pacific Daylight Time)

### `operator` (string, optional)
Company or crew that loaded the hole. Used for traceability and legal reporting. ENAEX does not include this; set from filename convention or constant in the adapter.

## Block G — Optional advanced fields

### `rock_mass_rating` (number, optional, range 0-100)
Bieniawski Rock Mass Rating (Bieniawski 1989). Required for Hoek-Brown factor-of-safety calculations. Provide separately via `core/geology.py` lookup if not in this file.

### `density_rock_t_m3` (number, optional, range 1.5-4.0)
In-situ rock density in tonnes/m³. Typical 2.6-2.8 for hard rock. Used to convert powder factor by mass to powder factor by volume.

### `initiation_system` (string, optional, enum)
Allowed values: `Nonel`, `Electronic`, `Detonating cord`, `Other`.

### `delay_ms` (number, optional)
Total delay in milliseconds from the blast reference time. ENAEX has `Secuencia` + `Retardo_ms`; total = sum.

### `bottom_hole_x/y/z` (numbers, optional)
Bottom-hole coordinates if downhole survey was performed. Required for accurate factor-of-safety calculations when hole deviation is significant.

### `decoupling_ratio` (number, optional)
Ratio of charge diameter to hole diameter. 1.0 = fully coupled (charge fills the hole). <1.0 = decoupled (e.g. charge sticks in air gap). Common: 0.95-1.0 for bulk-loaded, 0.5-0.8 for cartridge-loaded.

### `anomaly_flag` (string, optional, enum)
Allowed values: `loaded` (default, normal), `misfire` (did not detonate), `cutoff` (detonation stopped mid-hole), `wet_hole` (water in hole, partial loading), `bootleg` (unbroken stub at bottom), `refilled` (re-loaded after misfire), `empty` (no charge).

### `comment` (string, optional)
Free-text comment. Examples:
- `Detenido a 16 m por fractura`
- `Retacado con detritus, no con gravilla`
- `Carga parcial por presencia de agua`

## Unit summary

| Quantity | Unit | Symbol |
|---|---|---|
| Length | metre | m |
| Mass | kilogram | kg |
| Density | grams per cubic centimetre | g/cm³ |
| Density | tonnes per cubic metre | t/m³ |
| Angle | degree | ° |
| Time | second (or ISO-8601 with offset) | s |
| Delay | millisecond | ms |
| Coordinate | metre (in declared CRS) | m |

All units are SI. Conversions to imperial are the consumer's responsibility.