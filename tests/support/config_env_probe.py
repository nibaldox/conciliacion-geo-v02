"""Print a JSON snapshot of deployment settings captured at import time.

The values observed by ``core.config`` (and optionally ``api.main``) are
frozen when the modules are first imported, so this script must run in a
fresh interpreter with the environment already applied. It is used by
``tests/test_web_config_contracts.py`` to verify the import-time capture
contract without contaminating the pytest process.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(_REPO_ROOT))

    from core.config import DEFAULTS, DEPLOY

    snapshot = {
        "max_upload_mb": DEFAULTS.max_upload_mb,
        "log_format": DEPLOY.log_format,
        "workers": DEPLOY.workers,
    }
    if "--with-api" in argv:
        from api.main import _MAX_UPLOAD_BYTES

        snapshot["api_max_upload_bytes"] = _MAX_UPLOAD_BYTES

    json.dump(snapshot, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
