"""
Settings router — process settings and tolerance management.

Endpoints:
    GET  /settings   Return current settings merged with core defaults
    PUT  /settings   Update process and tolerance settings
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter

import api.database as db
import api.schemas as schemas
from core.config import DETECTION, TOLERANCES as DEFAULT_TOLERANCES

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_default_settings() -> dict:
    """Return default settings from core.config."""
    return {
        "process": {
            "resolution": DETECTION.profile_resolution,
            "face_threshold": DETECTION.face_threshold,
            "berm_threshold": DETECTION.berm_threshold,
        },
        "tolerances": {
            "bench_height": {
                "neg": DEFAULT_TOLERANCES.bench_height.get("neg", 1.0)
                if isinstance(DEFAULT_TOLERANCES.bench_height, dict)
                else DEFAULT_TOLERANCES.bench_height["neg"],
                "pos": DEFAULT_TOLERANCES.bench_height.get("pos", 1.5)
                if isinstance(DEFAULT_TOLERANCES.bench_height, dict)
                else DEFAULT_TOLERANCES.bench_height["pos"],
            },
            "face_angle": {
                "neg": DEFAULT_TOLERANCES.face_angle.get("neg", 5.0)
                if isinstance(DEFAULT_TOLERANCES.face_angle, dict)
                else DEFAULT_TOLERANCES.face_angle["neg"],
                "pos": DEFAULT_TOLERANCES.face_angle.get("pos", 5.0)
                if isinstance(DEFAULT_TOLERANCES.face_angle, dict)
                else DEFAULT_TOLERANCES.face_angle["pos"],
            },
            "berm_width": {
                "min": DEFAULT_TOLERANCES.berm_width.get("min", 6.0)
                if isinstance(DEFAULT_TOLERANCES.berm_width, dict)
                else DEFAULT_TOLERANCES.berm_width["min"],
            },
            "inter_ramp_angle": {
                "neg": DEFAULT_TOLERANCES.inter_ramp_angle.get("neg", 3.0)
                if isinstance(DEFAULT_TOLERANCES.inter_ramp_angle, dict)
                else DEFAULT_TOLERANCES.inter_ramp_angle["neg"],
                "pos": DEFAULT_TOLERANCES.inter_ramp_angle.get("pos", 2.0)
                if isinstance(DEFAULT_TOLERANCES.inter_ramp_angle, dict)
                else DEFAULT_TOLERANCES.inter_ramp_angle["pos"],
            },
            "overall_angle": {
                "neg": DEFAULT_TOLERANCES.overall_angle.get("neg", 2.0)
                if isinstance(DEFAULT_TOLERANCES.overall_angle, dict)
                else DEFAULT_TOLERANCES.overall_angle["neg"],
                "pos": DEFAULT_TOLERANCES.overall_angle.get("pos", 2.0)
                if isinstance(DEFAULT_TOLERANCES.overall_angle, dict)
                else DEFAULT_TOLERANCES.overall_angle["pos"],
            },
        },
    }


# ---------------------------------------------------------------------------
# GET /settings
# ---------------------------------------------------------------------------

@router.get("")
def get_settings():
    """
    Return current settings merged with core defaults.

    DB values override defaults; any missing key falls back to the
    corresponding value from core.config.
    """
    session_id = db.get_or_create_session()
    defaults = _get_default_settings()

    stored = db.get_settings(session_id)
    if not stored:
        return defaults

    # Deep merge: stored overrides defaults
    merged: Dict[str, Any] = {}
    for key in defaults:
        if key in stored:
            if isinstance(defaults[key], dict) and isinstance(stored[key], dict):
                merged[key] = {**defaults[key], **stored[key]}
            else:
                merged[key] = stored[key]
        else:
            merged[key] = defaults[key]

    return merged


# ---------------------------------------------------------------------------
# PUT /settings
# ---------------------------------------------------------------------------

@router.put("")
def update_settings(body: schemas.SettingsResponse):
    """
    Update process and tolerance settings.

    Accepts partial updates — only keys present in the body are changed;
    other settings retain their current values.
    """
    session_id = db.get_or_create_session()

    # Get existing settings or defaults
    existing = db.get_settings(session_id) or _get_default_settings()

    # Merge incoming body into existing settings
    body_dict = body.model_dump() if hasattr(body, "model_dump") else body.dict()

    if "process" in body_dict and body_dict["process"] is not None:
        if "process" not in existing:
            existing["process"] = {}
        existing["process"].update(body_dict["process"])

    if "tolerances" in body_dict and body_dict["tolerances"] is not None:
        if "tolerances" not in existing:
            existing["tolerances"] = {}
        existing["tolerances"].update(body_dict["tolerances"])

    db.save_settings(session_id, existing)

    return {"message": "Settings updated", "settings": existing}
