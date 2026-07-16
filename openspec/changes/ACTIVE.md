# Active Changes

> Single source of truth for in-flight SDD changes. The orchestrator
> updates this file as phases progress. Completed changes move to
> `archive/`.

| Change | Phase | Slice | Risk | Started | Proposal | Specs | Design | Tasks | Apply | Verify | Archive |
|---|---|---|---|---|---|---|---|---|---|---|---|
| _(No active changes.)_ | | | | | | | | | | | |

## Conventions

- One row per in-flight change.
- Phase column tracks the current `sdd-*` phase: `explore → proposal →
  spec → design → tasks → apply → verify → archive`.
- File links are relative to this directory.
- When a change moves to `archive/`, remove its row and append it to
  `archive/INDEX.md` (created by `sdd-archive`).

## Off-limits reminders (from `openspec/config.yaml` + `AGENTS.md`)

- `app.py`, `ui/`, `cli.py` — never modify.
- `core/__init__.py` — additive re-exports only.
- `web/`, `api/` — outside scope unless explicitly added to the change.