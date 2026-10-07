# Word Report Redesign Implementation Plan

**Goal:** Improve the generated geotechnical Word report's appearance without changing scientific calculations, result values, public export signatures or the protected Streamlit interface.

**Architecture:** Keep `core/report_generator.py` responsible for existing content and charts. Add a small python-docx presentation helper for document styles, cover, header/footer and table formatting. No new dependencies; no domain logic in the layout helper.

**Tech stack:** Python 3.12 in `.venv/Scripts/python.exe`, python-docx, OOXML, existing Matplotlib charts, pytest. Word is installed locally; LibreOffice is not available.

## Roles and ownership

Hermes is coordinator/reviewer only: write this plan and task briefs, inspect diffs, run existing commands, validate artifacts. All implementation, tests and rendering/demo scripts are written by coding subagents.

1. **Layout subagent:** owns `core/word_report_layout.py` and `tests/test_word_report_layout.py` only. Implements presentation helper via RED–GREEN cycles.
2. **Integration subagent:** after helper review, owns changes to `core/report_generator.py`, a new `tests/test_word_report_presentation.py`, and demo/render scripts under Hermes scratch only.
3. **Independent reviewer:** read-only review of implementation and tests; identify regressions, layout risks and scientific/metadata changes. Any fixes return to the owning coding subagent.

An initial read-only design audit runs in parallel with the layout subagent. The integration agent may write its RED tests and generator wiring against the agreed helper API while the helper is being completed; final tests/review must wait for both to finish. No concurrent writers share a file. No commits, push, installs, package-manager changes, remote calls, server restarts or real-session processing are authorized.

### Decisions after design audit

- Switch explicitly from the original Letter landscape to A4 landscape for technical table width.
- Retain original metadata semantics: full project/author in body paragraphs, missing keys `N/A`, blank strings unchanged, generation date as before; no operation/phase or invented branding.
- Use first-page furniture suppression; page counts include the cover, so the first body page is page 2.
- Bound image width AND height while preserving the native PNG aspect. Profile height budget must leave space for section heading, row labels and padding; do not alter chart geometry/H=V.
- Header/footer distances must sit inside margins. Long project names are abbreviated in the running header only; full text stays on the cover.
- Rendering may use a separate Word COM instance and page metafiles for PNG previews without installing dependencies. Any missing preview/renderer capability is reported rather than simulated.

## Design baseline

- Landscape A4 for wide technical tables, with consistent margins and restrained navy/teal/gray palette.
- A dedicated cover showing the existing report title, project, author and date; do not invent company names, logos, approvals or confidential classifications.
- Consistent Aptos/Calibri-compatible typography, heading hierarchy and spacing.
- Running project header and `Página PAGE de NUMPAGES` footer; cover without running furniture.
- Data tables with navy/white header, repeated header rows, modest cell padding, alternate pale row fill, aligned numeric columns and no split data rows.
- Preserve existing red/green status-cell fills and all status/value text. Never fabricate evaluable status for missing/extra results.
- Enlarged section profiles: two columns and four profiles per page, using the existing chart function and scale conventions.
- Major sections start clearly; avoid headings/captions orphaned from charts. Plan-view image gets a suitable dedicated page and bounded dimensions.

## Work unit 1: Presentation helper

**Create:** `core/word_report_layout.py`, `tests/test_word_report_layout.py`.

Agreed helper API:
- `configure_document(doc, project_info=None)` configures page/style/header/footer settings.
- `add_cover(doc, project_info=None)` adds cover and page break; preserves existing title and metadata labels.
- `style_data_table(table, column_weights=None)` formats a populated data table, fits it to usable width and preserves existing status fills/font colors.

Steps:
1. Read repository constraints and relevant current report code.
2. Write a small first behavioral test, run it and record the expected failure.
3. Implement the smallest slice to pass; repeat for page setup, furniture/fields, cover and table styling.
4. Cover empty/long metadata and preserving existing status shading.
5. Run `.venv/Scripts/python.exe -m pytest tests/test_word_report_layout.py -q` with isolated data/temp paths.
6. Hermes reviews source/diff/tests before integration.

Rollback boundary: remove the new helper/test files; no public behavior changes occur until integration.

## Work unit 2: Generator integration and regression protection

**Modify:** `core/report_generator.py`.
**Create:** `tests/test_word_report_presentation.py`; scratch-only reproducible demo/render harness.

Steps:
1. Add tests against the current generator proving desired cover/metadata, furniture, repeated table headers, preserved table data/status fills, and two-column profile layouts; run to observe RED before integration.
2. Call helper functions without changing the `generate_word_report` signature, scoring, comparison filtering, statistical aggregation, depth calculation, chart generation or data semantics.
3. Improve page breaks and profile image dimensions within usable A4 area; keep data tables readable.
4. Add a presentation fixture with multiple sections, plus empty report and long metadata cases. Test that comparison inputs are unchanged and formatted data retain current values.
5. Run focused report/export tests and generate demo DOCX with clearly identified synthetic data. Save demos only under `C:/Users/nibal/AppData/Local/hermes/cache/scratch/word-report-redesign/`.
6. Create a rendering harness using a separate Word COM instance, opened read-only, alerts disabled, PDF export to scratch, and reliable close/quit in finally. Do not close the user's existing Word instance or modify Office global settings. If COM/rendering is unavailable, report that explicitly and deliver DOCX without claiming visual validation.

Rollback boundary: undo only integration diff and its new regression tests/scripts; domain code remains unchanged.

## Work unit 3: Review and final validation

- Independent read-only review after both implementation units.
- Hermes inspects complete `git diff`, tests for visual contracts and preservation of data/signature.
- Run report-focused tests: `tests/test_word_report_layout.py`, `tests/test_word_report_presentation.py`, `tests/test_report_generator.py`, `tests/test_report_generator.py`'s existing scenarios, `tests/test_export_with_filters.py`, `tests/test_export_plan_view.py`, `tests/test_blast_export.py` and `tests/api/test_dxf_pipeline.py`.
- Run full backend suite excluding optional OpenBlast, sidecar packaging and largest benchmark: `.venv/Scripts/python.exe -m pytest tests/ -q --tb=short --ignore=tests/test_openblast.py --skip-electron --benchmark-skip-slow`. Record counts, warnings and exclusions.
- Run path-adapted existing synthetic pipeline in scratch, without editing its hardcoded `/tmp/` source paths.
- Read the produced DOCX and validate package health with the docx skill scripts.
- If Word rendering succeeds, inspect actual rendered cover, summary, table continuation and profile pages, and verify no blank/orphan/overflow pages.
- Deliver new demo DOCX and available PDF/preview, concise changes and actual verification results. Do not claim a published release.

## Acceptance criteria

1. Generated Word reports use the new formatting via the existing export path.
2. All original numeric values, comparison rows, metadata and public call signatures are preserved.
3. Tables repeat their headers and preserve current status indicators; plots remain within printable width and use existing geometry/scale behavior.
4. Empty inputs and long project/author strings generate a readable, valid document.
5. Tests are exercised with RED–GREEN evidence; final regression results and limitations are explicitly reported.
6. All code and tests are authored by subagents; Hermes only coordinates, reviews and validates.

## Known unrelated issues

The prior review found a TypeScript build error and API auth/deploy issues. They are outside this Word-design task; do not fix them or modify frontend/API behavior as part of this work.

## Final validation status (2026-10-07, validation executor)

- **Technical status: complete and validated on the frozen tree** (last source edit 10:38:55; every evidence run postdates it; no source changes were made during validation).
  - Full backend suite (single run, isolated TMP/TEMP/CONCILIACION_DATA_DIR, monitored to exit): **2371 passed, 8 skipped, 11 warnings** (exit 0; +54 tests vs pre-redesign 2317/8; exclusions: openblast, electron sidecar, slow benchmarks).
  - Focal set re-run: **97 passed** (matches prior 97-pass evidence).
  - Synthetic pipeline (path-adapted to scratch — NOT a literal unmodified invocation): **PASS** — 55 comparisons, 74.5% compliance; Excel (5 sheets) and Word (5 tables, 6 drawings) reopen.
  - Demo DOCX (3) pass the docx-skill validator; read-back records structure, status fills (C6EFCE/FFC7CE) and real sizes (1,047,402 / 312,227 / 38,333 bytes).
  - baseline-vs-new: no unexpected differences — public signatures, data-table text, status fills, paragraph tokens, input immutability and embedded image bytes equal.
  - AST audit: no public signature changes; chart/geometry functions (`create_section_plot`, `create_plan_view_image`, `create_compliance_pie_charts`, `generate_section_images_zip`) untouched; helper is presentation-only.
- **Visual limitation (blocked):** Word COM safe-render opened `demo_empty.docx` read-only and computed 3 pages, but `ExportAsFixedFormat` never returned (`safe-render/render_log.txt`); no PDF/PNG exists. Rendering was stopped by the coordinator; no retries authorized. **Visual layout/pagination remains UNVERIFIED — DOCX structural validity is not visual verification.**
- Static reviews: layout review passed=true (`word-layout-independent-review.md`); integration review passed=true (verdict preserved in `word-integration-review-agent.log`; its separate report file was never persisted). Both static, not visual.
- Evidence: `C:/Users/nibal/AppData/Local/hermes/cache/scratch/word-report-redesign/executor-evidence.md` (+ `logs/`).
