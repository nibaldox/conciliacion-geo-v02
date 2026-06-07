"""Entry point for the PyInstaller-bundled Python sidecar.

Launches uvicorn with the FastAPI app from api.main. The Electron main
process spawns this binary and talks to it over http://127.0.0.1:57890.

Environment variables set BEFORE importing api.database:
- CONCILIACION_DATA_DIR: directory for SQLite + logs + uploads
- DATABASE_URL: sqlite:///<data_dir>/conciliacion.db
"""

import logging
import os
import sys
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def resolve_data_dir() -> Path:
    """Resolve the per-OS data directory for the portable build.

    Windows: %APPDATA%/conciliacion/
    Linux:   $XDG_DATA_HOME/conciliacion/  (or ~/.local/share/conciliacion/)

    Raises:
        RuntimeError: if running on an unsupported platform.
    """
    if sys.platform == "win32":
        base = Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        )
    elif sys.platform.startswith("linux"):
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    else:
        raise RuntimeError(f"Plataforma no soportada: {sys.platform}")
    return base / "conciliacion"


def configure_data_dir() -> Path:
    """Resolve the data dir, create it, and export the relevant env vars.

    Returns:
        The data directory path.
    """
    data_dir = resolve_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(exist_ok=True)
    (data_dir / "uploads").mkdir(exist_ok=True)
    os.environ["CONCILIACION_DATA_DIR"] = str(data_dir)
    os.environ["DATABASE_URL"] = f"sqlite:///{data_dir}/conciliacion.db"
    return data_dir


def configure_logging(log_file: Path) -> None:
    """Send logs to a file under the data dir."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format=LOG_FORMAT,
    )


def main() -> None:
    data_dir = configure_data_dir()
    configure_logging(data_dir / "logs" / "conciliacion.log")

    import uvicorn
    from api.main import app

    uvicorn.run(app, host="127.0.0.1", port=57890, log_config=None)


if __name__ == "__main__":
    main()
