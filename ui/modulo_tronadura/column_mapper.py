"""Streamlit UI for schema-agnostic blast-hole column mapping.

Lets the user link their CSV/Excel columns to a canonical schema via dropdowns
before ``procesar_pozos`` (or any downstream consumer) ingests the file. If
the user skips the mapper (or every field matches an alias automatically),
the module also exposes a "use auto-suggested mapping" path so non-technical
users can keep moving without learning the schema.

Public API
----------
- ``render_column_mapper(df, key_prefix="blast")`` — render the widget block
  and return the final mapping dict, or ``None`` if the user has not
  confirmed yet (or explicitly skipped).

The mapping follows the contract defined in ``core.column_mapping``:
``{canonical_field_name: source_column_name | None}``.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.column_mapping import (
    REQUIRED_FIELDS,
    apply_mapping,
    auto_map,
    get_field_schema,
    validate_mapping,
)


# Sentinel used in the selectbox for "do not map this field".
_NO_MAP = "(no mapear)"

# Where the user's mapping (and confirm flag) lives. Per-invocation key_prefix
# keeps multiple uploaders (e.g. blast + design) from colliding.
_STATE_KEY_AUTO: str = "{prefix}_cm_auto_map"
_STATE_KEY_PERSISTED: str = "{prefix}_cm_persisted_mapping"
_STATE_KEY_LAST_HASH: str = "{prefix}_cm_last_df_hash"
_STATE_KEY_CONFIRMED: str = "{prefix}_cm_confirmed_mapping"


def _fingerprint(df: pd.DataFrame) -> tuple:
    """Cheap, stable fingerprint so we can detect a brand-new upload.

    Hashes the column-tuple (length + names). Does not depend on row order
    or row data, so reselecting the same file does not wipe the user's
    hand-tuned mapping.
    """
    cols = tuple(str(c) for c in df.columns)
    return (len(cols), cols)


def _restore_if_fresh(
    df: pd.DataFrame,
    key_prefix: str,
    auto_result,
) -> dict[str, str | None]:
    """Return the mapping to display: persisted edits if df has not changed,
    otherwise a copy of the freshly auto-detected mapping.

    Streamlit's widget state survives across reruns inside the same file,
    but the moment a new file is uploaded we want to start over with
    automatic detection — that is what the fingerprint guards against.
    """
    hash_key = _STATE_KEY_LAST_HASH.format(prefix=key_prefix)
    persisted_key = _STATE_KEY_PERSISTED.format(prefix=key_prefix)
    auto_key = _STATE_KEY_AUTO.format(prefix=key_prefix)

    fingerprint = _fingerprint(df)

    last_hash = st.session_state.get(hash_key)
    if last_hash != fingerprint:
        # New dataframe — seed both the persisted mapping (so the dropdowns
        # render the auto-suggestions) and the auto-suggested snapshot.
        st.session_state[persisted_key] = dict(auto_result.mapping)
        st.session_state[auto_key] = dict(auto_result.mapping)
        st.session_state[hash_key] = fingerprint
        st.session_state[_STATE_KEY_CONFIRMED.format(prefix=key_prefix)] = None
        return dict(auto_result.mapping)

    # Same dataframe — keep user's edits if any, else fall back to auto.
    persisted = st.session_state.get(persisted_key)
    if persisted is not None:
        return dict(persisted)
    return dict(auto_result.mapping)


def _persist(
    key_prefix: str,
    mapping: dict[str, str | None],
) -> None:
    st.session_state[_STATE_KEY_PERSISTED.format(prefix=key_prefix)] = dict(mapping)


def _confidence_label(conf: tuple[str, float]) -> str:
    kind, score = conf
    if kind == "exact":
        return "✓ exacto"
    if kind == "fuzzy":
        return f"~ {score:.0%}"
    return "— sin sugerencia"


def _render_field_row(
    field_def: dict[str, Any],
    source_columns: list[str],
    mapping: dict[str, str | None],
    key_prefix: str,
) -> str | None:
    """Render one selectbox for one canonical field and return the chosen source column.

    Writes the updated value back into ``mapping`` in place so the caller
    sees fresh selections on every rerun.
    """
    canonical = field_def["name"]
    description = field_def["description"]
    unit = field_def.get("unit") or ""
    aliases = field_def.get("aliases") or ()
    options = [_NO_MAP, *source_columns]

    current = mapping.get(canonical)
    default_index = 0
    if current in source_columns:
        default_index = options.index(current)
    elif current is None:
        default_index = 0

    label = f"**{canonical}**  ({description}"
    if unit:
        label += f" · {unit}"
    label += ")"

    with st.container():
        col_widget, col_aliases = st.columns([2, 3])
        with col_widget:
            widget_key = f"{key_prefix}_cm_field_{canonical}"
            chosen = st.selectbox(
                label,
                options=options,
                index=default_index,
                key=widget_key,
                help=(
                    f"Aliases conocidos: {', '.join(aliases[:6])}"
                    + ("…" if len(aliases) > 6 else "")
                ),
                label_visibility="visible",
            )
        with col_aliases:
            if aliases:
                st.caption("Aliases: " + ", ".join(aliases))
            else:
                st.caption("—")

    if chosen == _NO_MAP:
        mapping[canonical] = None
        return None
    mapping[canonical] = chosen
    return chosen


def _render_section(
    title: str,
    fields: list[dict[str, Any]],
    source_columns: list[str],
    mapping: dict[str, str | None],
    key_prefix: str,
    auto_conf: dict[str, tuple[str, float]],
    show_checkmarks: bool,
) -> None:
    """Render one group of fields (required or optional)."""
    st.markdown(f"#### {title}")
    for fdef in fields:
        canonical = fdef["name"]
        # status marker for required only
        if show_checkmarks:
            mapped_source = mapping.get(canonical)
            marker = "✓" if mapped_source else "⚠"
            conf = auto_conf.get(canonical, ("unmatched", 0.0))
            st.markdown(
                f"{marker} **{canonical}** — {fdef['description']} "
                f"  \n&nbsp;&nbsp;<small>{_confidence_label(conf)}</small>",
                unsafe_allow_html=True,
            )
        _render_field_row(fdef, source_columns, mapping, key_prefix)


def render_column_mapper(
    df: pd.DataFrame,
    key_prefix: str = "blast",
) -> dict[str, str | None] | None:
    """Render the column-mapping UI block.

    Args:
        df: The raw DataFrame the user just uploaded. The mapper never
            mutates it directly; it shows a preview after applying
            ``apply_mapping`` on a copy.
        key_prefix: A unique prefix for ``st.session_state`` keys so that
            different uploaders (blast, design, …) do not collide.

    Returns:
        - ``None`` while the user is still editing OR if they explicitly
          skipped mapping (the caller should fall back to legacy auto
          detection in that case).
        - A mapping dict ``{canonical: source | None}`` once the user
          confirms with the primary action button.
    """
    schema = get_field_schema()
    required: list[dict[str, Any]] = [f for f in schema if f["required"]]
    optional: list[dict[str, Any]] = [f for f in schema if not f["required"]]

    source_columns = [str(c) for c in df.columns]
    auto_result = auto_map(source_columns)
    mapping = _restore_if_fresh(df, key_prefix, auto_result)

    # ─── Header ────────────────────────────────────────────────────────────
    st.subheader("🔀 Mapeo de Columnas")
    st.write(
        f"Tu archivo tiene **{len(source_columns)} columnas** y "
        f"**{len(df)} filas**. Vincula cada campo canónico con una columna "
        f"de tu archivo, o deja *'{_NO_MAP}'* si no aplica. "
        f"Sugerimos mapeos automáticamente (✓ exacto, ≈ difuso)."
    )

    auto_conf = auto_result.confidence

    # ─── Two-column layout: required + optional ────────────────────────────
    left, right = st.columns(2)

    mapping_holder: dict[str, str | None] = mapping

    with left:
        _render_section(
            "Campos requeridos",
            required,
            source_columns,
            mapping_holder,
            f"{key_prefix}_req",
            auto_conf,
            show_checkmarks=True,
        )

    with right:
        _render_section(
            "Campos opcionales",
            optional,
            source_columns,
            mapping_holder,
            f"{key_prefix}_opt",
            auto_conf,
            show_checkmarks=False,
        )

    # Persist the latest selections (Streamlit reruns after every widget
    # change, and we want the next rerun to see what the user just picked).
    _persist(key_prefix, mapping_holder)

    # ─── Validation status ─────────────────────────────────────────────────
    errors = validate_mapping(mapping_holder)
    required_present = [
        f["name"] for f in required if mapping_holder.get(f["name"]) is not None
    ]
    required_missing = [
        f["name"] for f in required if mapping_holder.get(f["name"]) is None
    ]

    if not errors and len(required_present) == len(required):
        st.success(
            f"✅ {len(required_present)}/{len(required)} campos requeridos cubiertos. "
            "Listo para procesar."
        )
    elif required_missing:
        st.warning(
            f"⚠ Faltan {len(required_missing)} campos requeridos: "
            f"{', '.join(str(x) for x in required_missing)}"
        )
    else:
        for err in errors:
            st.error(err)

    # ─── Live preview ──────────────────────────────────────────────────────
    with st.expander("👀 Vista previa del mapeo (primeras 5 filas)", expanded=True):
        try:
            preview_df = apply_mapping(df.head(5), mapping_holder)
            st.dataframe(preview_df, width="stretch")
            st.caption(
                f"Columnas mapeadas: {len(preview_df.columns)} · "
                f"Filas válidas: {len(preview_df)} / 5"
            )
        except ValueError as exc:
            # apply_mapping raises if required fields are mapped to missing
            # source columns — show a soft preview of what we do have.
            st.info(
                f"Aún no se puede generar la vista previa: {exc}. "
                "Selecciona todas las columnas requeridas para habilitarla."
            )

    # ─── Actions ───────────────────────────────────────────────────────────
    btn_col, info_col = st.columns([2, 3])
    with btn_col:
        can_confirm = len(errors) == 0 and not required_missing
        if st.button(
            "✅ Confirmar mapeo y procesar",
            type="primary",
            disabled=not can_confirm,
            key=f"{key_prefix}_cm_confirm",
            help=(
                "Bloqueado hasta que todas las columnas requeridas estén "
                "asignadas y no haya duplicados."
                if not can_confirm
                else "Confirma el mapeo y devuelve el dict al módulo de procesamiento."
            ),
        ):
            confirmed = dict(mapping_holder)
            # Drop keys mapped to None for a cleaner payload.
            confirmed = {k: v for k, v in confirmed.items() if v is not None}
            st.session_state[_STATE_KEY_CONFIRMED.format(prefix=key_prefix)] = confirmed
            return confirmed
    with info_col:
        st.caption(
            f"Sugerencias automáticas: "
            f"{sum(1 for k, (kind, _) in auto_conf.items() if kind == 'exact')} exactas · "
            f"{sum(1 for k, (kind, _) in auto_conf.items() if kind == 'fuzzy')} difusas · "
            f"{sum(1 for k, (kind, _) in auto_conf.items() if kind == 'unmatched')} sin sugerencia"
        )

    # If the user already confirmed in a previous rerun, return that.
    previously_confirmed = st.session_state.get(
        _STATE_KEY_CONFIRMED.format(prefix=key_prefix)
    )
    if previously_confirmed is not None:
        return previously_confirmed

    return None


def get_confirmed_mapping(key_prefix: str = "blast") -> dict[str, str | None] | None:
    """Convenience accessor for the last confirmed mapping, if any.

    Callers that want to fetch the mapping outside ``render_column_mapper``
    (e.g. background jobs, cached processors) can use this instead of fishing
    through ``st.session_state`` directly.
    """
    return st.session_state.get(_STATE_KEY_CONFIRMED.format(prefix=key_prefix))


def clear_confirmed_mapping(key_prefix: str = "blast") -> None:
    """Reset the confirmed mapping (useful after a new upload)."""
    st.session_state[_STATE_KEY_CONFIRMED.format(prefix=key_prefix)] = None


__all__ = [
    "render_column_mapper",
    "get_confirmed_mapping",
    "clear_confirmed_mapping",
    "REQUIRED_FIELDS",
]
