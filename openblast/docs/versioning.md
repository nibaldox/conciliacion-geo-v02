# OpenBlast Versioning Policy

OpenBlast follows **Semantic Versioning 2.0.0** ([semver.org](https://semver.org/)).

## Identifier

Every OpenBlast file carries the format identifier either explicitly (in the `datapackage.json` `openblast_version` field, or as a CSV comment `# openblast_version: 1.0.0`) or implicitly (by virtue of being processed by an OpenBlast x.y parser).

## Versioning rules

### MAJOR version bump (breaking)

- Renaming a mandatory field
- Changing the data type of a mandatory field (e.g. `string → number`)
- Removing a mandatory field
- Changing the units of a mandatory field (e.g. `m → ft`)
- Adding a new mandatory field
- Changing the format of `shot_at` (e.g. ISO-8601 → epoch seconds)
- Changing the enum values of a mandatory field in a non-backward-compatible way

### MINOR version bump (backward-compatible additions)

- Adding a new **optional** field
- Adding a new value to an enum that is also new (e.g. adding `Slurry` to `explosive_type`)
- Adding a new file in `mappings/` for an additional vendor
- Adding a new example file in `examples/`

### PATCH version bump (backward-compatible fixes)

- Fixing a typo in a field description (no semantic change)
- Tightening or loosening `minimum` / `maximum` constraints without changing the semantic range
- Improving documentation, examples, or comments
- Adding new test cases

## Backward compatibility guarantees

- Within a **MAJOR** version, all `MINOR.PATCH` releases are guaranteed to be readable by a parser written for the MAJOR version.
- A `1.0` parser must read `1.1.5` files. It may ignore new optional fields it doesn't understand.
- Across MAJOR versions, no compatibility guarantee. Each MAJOR bump must ship with a `docs/migrations/X-1.x-to-X.md` migration guide.

## Deprecation policy

- A field marked `deprecated: true` in the schema will continue to be supported for **at least one additional MAJOR version** (typically 6-12 months).
- Deprecated fields are listed in `docs/migrations/` with migration notes.
- Removal of a deprecated field is allowed only at a MAJOR version bump.

## Example change log

| Version | Date | Type | Description |
|---|---|---|---|
| 1.0.0 | 2026-06-20 | MAJOR | Initial release. 17 mandatory + 17 optional fields. |
| 1.1.0 | (planned) | MINOR | Add optional `fragmentation_p50_mm`, `fragmentation_p80_mm` fields for post-blast image analysis. |
| 1.2.0 | (planned) | MINOR | Add optional multi-table support via `datapackage.json` for sites that separate survey from collar. |
| 2.0.0 | (future) | MAJOR | Add `initiation_pattern` as mandatory field for vibration modelling; migrate `shot_at` to epoch milliseconds. Migration guide will be provided. |

## How to specify OpenBlast version in your tooling

When implementing an OpenBlast parser:

```python
SUPPORTED_OPENBLAST_VERSIONS = ["1.x"]
MIN_OPENBLAST_VERSION = "1.0.0"
```

If you encounter a file with a higher `openblast_version` than your parser supports, warn the user but attempt to read it anyway — the new fields will just be ignored. If the file's `openblast_version` has a different MAJOR version than your parser supports, refuse to read it and tell the user to upgrade.