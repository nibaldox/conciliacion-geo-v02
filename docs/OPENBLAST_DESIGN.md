# OpenBlast — Formato CSV agnóstico para Perforación y Tronadura

> **Estado**: diseño v1.0 (RFC).
> **Repositorio**: pendiente de crear.
> **Maintainer**: equipo `conciliacion-geo`.

---

## Motivación

El proyecto `conciliacion-geo-v02` consume archivos CSV/XLSX de pozos de tronadura para calcular powder factor, recomendar ajustes de carga, y correlacionar daño geotécnico con energía de voladura. Hoy depende del **formato propietario de ENAEX** (las columnas exactas de `enaex_pozos_tronadura_2026.xlsx`), lo que:

1. **Bloquea adopción comunitaria**: solo quienes usan ENAEX como operador pueden subir datos.
2. **Acopla el sistema a un vendor chileno**: cambia el formato y se rompe todo.
3. **Dificulta portabilidad de datos**: ingenieros que migran de MinePlan, Datamine, Surpac, Vulcan o plantillas Excel ad-hoc deben re-mapear a mano.

**OpenBlast** es una propuesta de **formato CSV vendor-neutral**, autovalidable (JSON Schema Draft-07), versionado (SemVer), y extensible para que la comunidad open-source adopte sin atarse a un proveedor.

---

## Resumen ejecutivo

| Item | Decisión |
|---|---|
| **Nombre** | `OpenBlast` v1.0 |
| **Formato base** | CSV plano (RFC 4180) |
| **Validación** | JSON Schema Draft-07 |
| **Versionado** | SemVer 2.0 sobre identificador de formato |
| **Extensibilidad** | `additionalProperties: true` para columnas vendor-specific |
| **Mínimo viable** | 17 campos obligatorios + 17 opcionales |
| **Mapeos documentados** | ENAEX, Datamine, MinePlan, Surpac, Vulcan, acQuire, Orica |
| **Tooling** | `openblast-validate` (CLI), `openblast-convert` (CLI), `openblast` (PyPI) |

---

## Contexto técnico: panorama de estándares

### Estándares revisados (no cubren nuestro caso)

| Estándar | URL | Veredicto |
|---|---|---|
| ISO 19156:2011/2023 Observations & Measurements | https://committee.iso.org/sites/tc211/home/projects/projects---complete-list/iso-19156.html | Modelo conceptual XML/GML; sirve de marco teórico pero no da CSV. |
| GeoSciML v4.1 | http://geosciml.org/ | Geología mapeada; no cubre tronadura operacional. |
| EarthResourceML v2.0 | https://earthresourceml.org/ | Mineral occurrences; no llega a nivel de pozo cargado. |
| Open Mining Format (OMF) v1.0.1 | https://gmggroup.org/projects/open-mining-format-omf/ | Binario `.omf`; útil para block models, no para "una fila por pozo". |
| Datamine drillhole format | https://docs.dataminesoftware.com/StudioNPVS/Latest/Process_Help_XML/holes3d.htm | Estándar **de facto** para exploración, no para producción. |
| Surpac Drillhole DB | https://help.seequent.com/Oasismontaj/2023.1/Content/gxhelp/drillhole/dhexpsurpacgd_gx.htm | Equivalente a Datamine (tablas `collar`/`survey`/`assay`). |
| Frictionless Data Table Schema | https://specs.frictionlessdata.io/table-schema/ | **Adoptado como capa de metadatos** del CSV. |
| CSV on the Web (W3C) | https://www.w3.org/TR/csvw-ucr/ | Alternativa a Frictionless; ambos válidos. |

### Laguna detectada

Ningún estándar open-source cubre "una fila por pozo cargado con explosivos para reconciliación geotécnica". OMF/Datamine/Surpac apuntan a exploration drillholes. GeoSciML/EarthResourceML son demasiado generales. ENAEX tiene lo más cercano al dominio operacional pero es opaco y propietario.

**Oportunidad**: un CSV canónico con JSON Schema adoptable desde Datamine, MinePlan, Surpac, ENAEX, o cualquier script Python, trivial de validar con `jsonschema`.

---

## Diseño de campos

### Convención de nombres

- `snake_case` (alineado con Python/pandas/Datamine).
- Sin tildes ni `ñ`.
- Unidades SI declaradas en el schema.
- Inglés (con tabla de mapeos a nombres en español en `/openblast/mappings/`).

### Bloque A — Identificación del pozo (obligatorio)

| Campo | Tipo | Unidad | Ejemplo | Equivalencia |
|---|---|---|---|---|
| `hole_id` | string | — | `ZH-1423-A` | ENAEX `Nombre`, Datamine `BHID` |
| `blast_id` | string | — | `POLV-2026-04-12-A` | ENAEX (concatenar polígono + fecha) |
| `sequence` | integer | — | `3` | ENAEX `Secuencia`, Datamine `delay` |

### Bloque B — Localización y orientación (obligatorio)

| Campo | Tipo | Unidad | Ejemplo | Equivalencia |
|---|---|---|---|---|
| `easting` | number | m | `421587.32` | ENAEX `Longitud_Geo`, Datamine `XCOLLAR` |
| `northing` | number | m | `7289431.05` | ENAEX `Latitud_Geo`, Datamine `YCOLLAR` |
| `elevation` | number | m | `3145.7` | ENAEX (derivar), Datamine `ZCOLLAR` |
| `dip` | number | grados (-90 a 90) | `-65.0` | ENAEX `Inclinacion_real`, Datamine `DIP` |
| `azimuth` | number | grados (0-360) | `127.5` | ENAEX `Azimuth_real`, Datamine `BRG` |

### Bloque C — Geometría del pozo (obligatorio)

| Campo | Tipo | Unidad | Ejemplo | Equivalencia |
|---|---|---|---|---|
| `hole_length_planned` | number | m | `16.5` | ENAEX `Longitud_teo` |
| `hole_length_actual` | number | m | `16.2` | ENAEX `longitud_real`, Datamine `LENGTH` |
| `diameter_mm` | number | mm | `311.0` | ENAEX `diametro` (mm) o `diametro_pulgada` (×25.4) |
| `burden` | number | m | `7.5` | ENAEX (no incluido, derivar de malla) |
| `spacing` | number | m | `8.5` | ENAEX (no incluido, derivar de malla) |
| `subdrill` | number | m | `1.2` | ENAEX (no incluido) |

### Bloque D — Carga de explosivo (obligatorio)

| Campo | Tipo | Unidad | Ejemplo | Equivalencia |
|---|---|---|---|---|
| `explosive_type` | string (enum) | — | `Heavy ANFO` | ENAEX `Nombre` |
| `explosive_kg_actual` | number | kg | `385.4` | ENAEX `Kilos_Cargados_real` |
| `explosive_kg_planned` | number | kg | `400.0` | ENAEX `Kilos_Cargados_teo` |
| `explosive_density_g_cc` | number | g/cm³ | `1.15` | ENAEX (raro) |

### Bloque E — Taco / stemming (obligatorio)

| Campo | Tipo | Unidad | Ejemplo | Equivalencia |
|---|---|---|---|---|
| `stemming_length_m` | number | m | `4.2` | ENAEX `stemming_real` |

### Bloque F — Metadatos y trazabilidad (obligatorio)

| Campo | Tipo | Unidad | Ejemplo | Equivalencia |
|---|---|---|---|---|
| `mine_site` | string | — | `Zalivar` | ENAEX `Nombre_Rajo` |
| `bench_id` | string | — | `B-3140` | ENAEX `Nombre_Banco` |
| `shot_at` | string (ISO-8601) | UTC offset | `2026-04-12T13:42:00-03:00` | ENAEX `fecha_tronadura` |
| `operator` | string | — | `ENAEX-Zalivar` | ENAEX (metadata) |

### Bloque G — Opcionales (recomendados pero no obligatorios)

- `rock_mass_rating` (RMR/GSI, 0-100)
- `density_rock_t_m3` (densidad de roca, t/m³)
- `initiation_system` (Nonel, Electronic, Detonating cord)
- `delay_ms` (delay total en ms)
- `bottom_hole_x/y/z` (coordenadas del fondo si hubo survey)
- `emulsion_kg`, `anfo_kg`, `bulk_kg` (desglose por tipo si la carga es mixta)
- `decoupling_ratio` (ratio diámetro carga / diámetro pozo)
- `comment` (texto libre)
- `anomaly_flag` (enum: `loaded`, `misfire`, `cutoff`, `wet_hole`, `bootleg`, `refilled`, `empty`)

---

## Política de versionado (SemVer 2.0.0)

| Cambio | MAJOR | MINOR | PATCH |
|---|---|---|---|
| Renombrar campo obligatorio | ✅ | | |
| Cambiar tipo de campo obligatorio | ✅ | | |
| Eliminar campo obligatorio | ✅ | | |
| Cambiar unidades de campo obligatorio | ✅ | | |
| Añadir campo obligatorio nuevo | ✅ | | |
| Cambiar formato de `shot_at` | ✅ | | |
| Añadir campo opcional nuevo | | ✅ | |
| Añadir valor a un `enum` (compatible) | | ✅ | |
| Corregir typo en descripción | | | ✅ |
| Corregir `minimum`/`maximum` sin cambiar semántica | | | ✅ |

**Compatibilidad garantizada** dentro de la misma MAJOR. `1.x` debe leer `1.0`, `1.1`, etc.

---

## Tabla de equivalencias entre vendors (resumen)

| OpenBlast | ENAEX | Datamine | MinePlan | Surpac | Vulcan | acQuire | Orica |
|---|---|---|---|---|---|---|---|
| `hole_id` | `Nombre` | `BHID` | `BHID` | `HoleID` | `hole_id` | `HOLE_ID` | `HoleID` |
| `blast_id` | (concat) | (derivar) | (derivar) | (derivar) | (derivar) | `ProjectCode` | `BlastId` |
| `sequence` | `Secuencia` | (derivar) | (derivar) | `seq` | `sequence` | (custom) | `Sequence` |
| `easting` | `Longitud_Geo` | `XCOLLAR` | `XCOLLAR` | `XCOLLAR` | `X` | `HoleLocation.X` | `Easting` |
| `northing` | `Latitud_Geo` | `YCOLLAR` | `YCOLLAR` | `YCOLLAR` | `Y` | `HoleLocation.Y` | `Northing` |
| `elevation` | (derivar) | `ZCOLLAR` | `ZCOLLAR` | `ZCOLLAR` | `Z` | `HoleLocation.Z` | `Elevation` |
| `dip` | `Inclinacion_real` | `DIP` | `DIP` | `DIP` | `dip` | `Dip` | `Dip` |
| `azimuth` | `Azimuth_real` | `BRG` | `BRG` | `BRG` | `bearing` | `Azimuth` | `Bearing` |
| `hole_length_planned` | `Longitud_teo` | (calcular) | (calcular) | `length_planned` | (custom) | `PlannedDepth` | `PlannedDepth` |
| `hole_length_actual` | `longitud_real` | `LENGTH` | `LENGTH` | `LENGTH` | `depth` | `ActualDepth` | `ActualDepth` |
| `diameter_mm` | `diametro` o `diametro_pulgada`×25.4 | (custom) | (custom) | (custom) | `diameter` | (custom) | `HoleDiam` |
| `burden` | (no incluido) | (calcular) | (calcular) | (calcular) | (custom) | (custom) | `Burden` |
| `spacing` | (no incluido) | (calcular) | (calcular) | (calcular) | (custom) | (custom) | `Spacing` |
| `subdrill` | (no incluido) | (custom) | (custom) | (custom) | `subdrill` | (custom) | `Subdrill` |
| `explosive_type` | `Nombre` | (custom) | (custom) | (custom) | (custom) | (custom) | `Product` |
| `explosive_kg_actual` | `Kilos_Cargados_real` | (custom) | (custom) | (custom) | (custom) | (custom) | `ChargeMass` |
| `explosive_kg_planned` | `Kilos_Cargados_teo` | (custom) | (custom) | (custom) | (custom) | (custom) | `PlannedMass` |
| `stemming_length_m` | `stemming_real` | (custom) | (custom) | (custom) | (custom) | (custom) | `Stemming` |
| `mine_site` | `Nombre_Rajo` | `PROJECT` | `PROJECT` | `project` | `project` | `ProjectCode` | `Site` |
| `bench_id` | `Nombre_Banco` | `BENCH` | `BENCH` | `bench` | `bench` | (custom) | `Bench` |
| `shot_at` | `fecha_tronadura` | (custom) | (custom) | (custom) | (custom) | (custom) | `ShotTime` |
| `anomaly_flag` | `Estado` | (custom) | (custom) | (custom) | (custom) | (custom) | `Status` |

---

## Roadmap de adopción

### Fase 1 — Artefactos del formato (2-3 días)

```
openblast/
├── README.md
├── LICENSE (Apache-2.0 recomendado)
├── CHANGELOG.md
├── VERSION
├── schema/
│   ├── openblast-1.0.0.schema.json
│   └── openblast-1.0.0.table-schema.json (Frictionless)
├── examples/
│   ├── minimal.csv
│   ├── complete.csv
│   ├── datapackage.json
│   └── zalivar-blasts-2026-sample.csv
├── mappings/
│   ├── enaex-to-openblast.csv
│   ├── datamine-to-openblast.csv
│   ├── mineplan-to-openblast.csv
│   ├── surpac-to-openblast.csv
│   └── vulcan-to-openblast.csv
├── docs/
│   ├── specification.md
│   ├── field-reference.md
│   ├── versioning.md
│   └── migrations/1.0.0-initial.md
└── tools/
    ├── openblast-validate.py (CLI)
    ├── openblast-convert.py (CLI)
    └── pyproject.toml (pip install)
```

### Fase 2 — Integración con el proyecto (3-5 días)

1. Adapter `OpenBlastAdapter` en `src/adapters/` que lee `holes.csv` y valida con JSON Schema.
2. Mantener `ENAEXAdapter` como legacy con link al mapeo.
3. Detector automático de formato por heurística sobre primeras filas.
4. Tests: `tests/adapters/test_openblast.py` con happy path, columnas faltantes, tipos incorrectos.
5. README del proyecto: priorizar OpenBlast como formato preferido.

### Fase 3 — Tooling público (3-5 días)

```bash
pip install openblast
openblast-validate path/to/holes.csv
openblast-convert --from enaex enaex.xlsx --to openblast holes.csv
openblast inspect holes.csv --report powder-factor
```

### Fase 4 — Publicación y comunidad (1-2 semanas)

1. Publicar `openblast/` como subdirectorio del repo.
2. Tag `v1.0.0`.
3. Crear repo independiente `conciliacion-geo/openblast-spec`.
4. Publicar en PyPI.
5. Post en `r/mining`, `r/MiningEngineering`, foros de GMG.
6. Someter como draft a GMG para reconocimiento oficial.

### Fase 5 — Evolución

- **v1.1** (3-6 meses): vibración (PPV), fragmentación (P50/P80), survey.
- **v1.2** (6-12 meses): multi-tabla opcional vía `datapackage.json`.
- **v2.0** (12-18 meses, si comunidad lo pide): secondary breaking, MWD, digital twin.

---

## Referencias validadas

- https://earthresourceml.org/
- https://specs.frictionlessdata.io/table-schema/
- https://specs.frictionlessdata.io/data-package/
- https://gmggroup.org/projects/open-mining-format-omf/
- https://github.com/gmggroup/omf
- https://docs.dataminesoftware.com/StudioNPVS/Latest/Process_Help_XML/holes3d.htm
- https://docs.dataminesoftware.com/StudioRM/Latest/Process_Help_XML/desurv.htm
- https://help.seequent.com/Oasismontaj/2023.1/Content/gxhelp/drillhole/dhexpsurpacgd_gx.htm
- https://help.maptek.com/mapteksdk/1.5/topics/object-types/drillholes.htm
- https://github.com/opengeostat/PyGSLIB_Tutorial/blob/master/Tutorial_V2.ipynb
- https://portal.ogc.org/files/?artifact_id=41579 (ISO 19156 PDF)
- https://committee.iso.org/sites/tc211/home/projects/projects---complete-list/iso-19156.html

---

## Licencia propuesta

`Apache-2.0` (preferida a MIT por la cláusula de patente explícita, importante para estándares industriales).

---

**Fin del documento de diseño.** Las fases 1-5 son las que se ejecutarán a continuación.