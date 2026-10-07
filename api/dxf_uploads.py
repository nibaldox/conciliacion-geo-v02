import os
import sys
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
_uploads: dict[str, dict] = {}
_lock = threading.RLock()
_parse_slots = threading.BoundedSemaphore(2)
_ttl_seconds = 15 * 60
_max_pending_files = 8
_max_pending_bytes = 1024 * 1024 * 1024
_pending_root = Path(tempfile.gettempdir()) / "conciliacion-dxf-pending"
_pending_root.mkdir(parents=True, exist_ok=True)
_resolved_pending_root = _pending_root.resolve(strict=True)
_instance_dir = _pending_root / f"{os.getpid()}-{uuid.uuid4().hex}"
_instance_dir.mkdir()
_resolved_instance_dir = _instance_dir.resolve(strict=True)


def _is_managed_directory(path: Path) -> bool:
    try:
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            return False
        return path.resolve(strict=True).parent == _resolved_pending_root
    except (FileNotFoundError, OSError):
        return False


def _process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87
        exit_code = wintypes.DWORD()
        try:
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


for _candidate in _pending_root.iterdir():
    try:
        if _candidate == _instance_dir or not _candidate.is_dir() or not _is_managed_directory(_candidate):
            continue
        _owner_pid = int(_candidate.name.split("-", 1)[0])
        if _owner_pid is not None and _process_alive(_owner_pid):
            continue
        if _owner_pid is not None:
            shutil.rmtree(_candidate.resolve(strict=True), ignore_errors=True)
    except (FileNotFoundError, ValueError):
        pass


def create_temp_file() -> tuple[int, str]:
    _instance_dir.mkdir(parents=True, exist_ok=True)
    return tempfile.mkstemp(prefix="upload-", suffix=".dxf", dir=_instance_dir)


def _remove(upload: dict) -> None:
    try:
        os.unlink(upload["path"])
    except FileNotFoundError:
        pass


def cleanup_expired() -> None:
    now = time.monotonic()
    with _lock:
        expired = [key for key, value in _uploads.items() if value["expires"] <= now and not value["claimed"]]
        for key in expired:
            _remove(_uploads.pop(key))


def store(path: str, session_id: str, filename: str, mesh_type: str, size: int) -> dict:
    cleanup_expired()
    upload_id = str(uuid.uuid4())
    expires = time.monotonic() + _ttl_seconds
    with _lock:
        session_uploads = [key for key, value in _uploads.items() if value["session_id"] == session_id]
        same_role = [key for key in session_uploads if _uploads[key]["type"] == mesh_type and not _uploads[key]["claimed"]]
        for key in same_role:
            _remove(_uploads.pop(key))
        if len(_uploads) >= _max_pending_files or sum(value["size"] for value in _uploads.values()) + size > _max_pending_bytes:
            raise ValueError("DXF_PENDING_LIMIT: demasiados archivos temporales; cancele una inspección e intente nuevamente.")
        if len(session_uploads) >= 2 and not same_role:
            raise ValueError("DXF_SESSION_PENDING_LIMIT: ya hay una inspección pendiente para ambos roles.")
        _uploads[upload_id] = {
            "path": path,
            "session_id": session_id,
            "filename": filename,
            "type": mesh_type,
            "expires": expires,
            "size": size,
            "claimed": False,
        }
    return {"upload_id": upload_id, "filename": filename, "type": mesh_type, "expires_at": int(time.time() + _ttl_seconds)}


def get(upload_id: str, session_id: str) -> dict | None:
    cleanup_expired()
    with _lock:
        value = _uploads.get(upload_id)
        if value is None or value["session_id"] != session_id:
            return None
        return dict(value)


def take(upload_id: str, session_id: str) -> dict | None:
    cleanup_expired()
    with _lock:
        value = _uploads.get(upload_id)
        if value is None or value["session_id"] != session_id or not value["claimed"]:
            return None
        return _uploads.pop(upload_id)


def claim(upload_id: str, session_id: str) -> dict | None:
    cleanup_expired()
    with _lock:
        value = _uploads.get(upload_id)
        if value is None or value["session_id"] != session_id or value["claimed"]:
            return None
        value["claimed"] = True
        return dict(value)


def release(upload_id: str, session_id: str) -> None:
    with _lock:
        value = _uploads.get(upload_id)
        if value is not None and value["session_id"] == session_id:
            value["claimed"] = False


def cleanup_all() -> None:
    with _lock:
        for upload in _uploads.values():
            _remove(upload)
        _uploads.clear()
        if _is_managed_directory(_instance_dir):
            shutil.rmtree(_resolved_instance_dir, ignore_errors=True)


def cancel(upload_id: str, session_id: str) -> bool:
    cleanup_expired()
    with _lock:
        value = _uploads.get(upload_id)
        if value is None or value["session_id"] != session_id or value["claimed"]:
            return False
        _remove(_uploads.pop(upload_id))
        return True


def parse_dxf(fn, *args, **kwargs):
    with _parse_slots:
        return fn(*args, **kwargs)
