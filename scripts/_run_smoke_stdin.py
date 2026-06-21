"""Helper: run the smoke test with the API key from stdin or a file.

Usage:
    # Option A: pipe the key
    echo "$OPENROUTER_API_KEY" | python scripts/_run_smoke_stdin.py

    # Option B: read from a file
    python scripts/_run_smoke_stdin.py < /path/to/keyfile

    # Option C: read from env (if your shell supports it)
    OPENROUTER_API_KEY='***' python scripts/_run_smoke_stdin.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        if not sys.stdin.isatty():
            key = sys.stdin.read().strip()
    if not key:
        print("ERROR: no key provided via env or stdin", file=sys.stderr)
        sys.exit(1)
    repo = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["OPENROUTER_API_KEY"] = key
    env["PYTHONPATH"] = str(repo)
    cmd = [sys.executable, str(repo / "scripts" / "smoke_ai_v2_openrouter.py")]
    result = subprocess.run(cmd, env=env, cwd=repo)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()