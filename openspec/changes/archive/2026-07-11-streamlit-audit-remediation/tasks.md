# Tasks: streamlit-audit-remediation

> Behavior-preserving remediation of 11 audit findings on `app.py` + `ui/`. `core/__init__.py` untouched.

## Review Workload Forecast

Estimated changed lines: +260/-260 across 13 modified + 1 new file. 400-line risk: Low. 800-line risk: Low. Chained PRs: No. Delivery strategy: ask-always. Chain strategy: size-exception. Highest-risk: H5.

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

Commit order: CRITICAL -> HIGH -> MEDIUM -> LOW inside one PR; H5 last of HIGH for bisect.

## Phase 1: CRITICAL

- [x] 1.1 C1: ui/step1_upload.py L45-57 - insert cache_resource.clear() + cache_data.clear() before mesh-null lines + st.rerun(). ui/plots.py:62 - doc _mesh + clear contract.
- [x] 1.2 C2a: core/blast_correlation.py - copy compute_monthly_trend, detect_pf_outliers_iqr, split_campaign verbatim from tests/test_ai_service_enrich.py L5-107; append __all__.
- [x] 1.3 C2b: tests/test_ai_service_enrich.py L1-2 - replace module defs with `from core.blast_correlation import (...)`; test bodies unchanged.
- [x] 1.4 C2c: ui/tabs/blast_correlation.py L28-36 - drop try/except ImportError for tests.test_ai_service_enrich; unconditional import from core.blast_correlation; drop _HAS_TREND_HELPERS.

## Phase 2: HIGH

- [x] 2.1 H1: ui/step2_sections.py L29-31, L259, L324 - delete _cached_local_azimuth; call compute_local_azimuth(mesh_d, np.array([ox, oy])) direct.
- [x] 2.2 H2a: ui/filters.py - add _collect_active_filters_from_session_state() -> dict[str, list] (4-key active-filters dict).
- [x] 2.3 H2b: dashboard.py L31-38, export.py L51-72/127/213, ai_report.py L212-236/371-374 - delete _get_filtered_comparisons + local _filters_summary; collapse _apply_table_filters to delegate; import filters_summary from ui.filters.
- [x] 2.4 H3: ui/tabs/table.py L101-113 - delete dead _highlight_status; live highlight_status from ui.labels (L24) unchanged.
- [x] 2.5 H4: ui/sidebar.py L38 - st.slider 0..30 default int(DETECTION.berm_threshold).
- [x] 2.6 H5a: NEW ui/_blast_correlation_shared.py - export project_powder_factor_per_section (pure kernel) + build_pf_deviation_scatter(..., show_ols=False).
- [x] 2.7 H5b: ui/modulo_tronadura.py L391-562 - replace kernel with shared import; preserve signed split, OLS on over, Pearson caption. Net -150 LOC.
- [x] 2.8 H5c: ui/tabs/blast_correlation.py L384-480 - shared import for sec/banco/malla variants (show_ols=False). H5 acceptance: pre/post diff-test on synthetic 4-section DataFrame - table cols, axes, scales, log lines byte-identical.

## Phase 3: MEDIUM

- [x] 3.1 M1: sweep ui/** 33 hits - use_container_width=True -> width="stretch". app.py: confirm 0 hits.
- [x] 3.2 M2: ui/tabs/ai_report.py L17/L135 - swap to streamlit.components.v2; register components.component once; wrap L135 in _html_button(payload, key) height="42px". No swap to st.iframe.
- [x] 3.3 M4a: ui/step2_sections.py _render_tab_manual L337-342 - append with _N suffixing (copy L119-129 loop).
- [x] 3.4 M4b: _render_tab_auto L391-395 - same append+suffix pattern.
- [x] 3.5 M4c: _render_sections_table L418 - banner "Total acumulado: N secciones".

## Phase 4: LOW

- [x] 4.1 L1: ui/modulo_tronadura.py L265/298/342/402/624/684/913 - drop redundant `import numpy as np` / `import pandas as pd`.
- [x] 4.2 L2: ui/step2_sections.py apply handlers (L132/285/342/395) - after sections.append, add st.session_state.pop('_profile_figs', None).
- [x] 4.3 L3: ui/ref_lines.py L108 - z_value: float = None -> z_value: Optional[float] = None (or PEP 604 `float | None`); import Optional if missing.
- [x] 4.4 L4: ui/step2_sections.py L107 - drop redundant `import os` (already at L10); keep if used.

## Apply-phase verification

- pytest tests/ -v --tb=short (skip test_openblast.py if missing) - green.
- python test_pipeline.py - green.
- Manual Streamlit run-through; cache-clear log visible (C1).
- rg invariants from spec + design - all zero/positive.