"""App icons: extracted from each program's .exe with Windows' own icon API, cached as small PNGs.

Only paths that Windows itself reported in its usage history, that end in .exe and exist, are used. Paths go to
PowerShell through a JSON file (never inside the script text). Icons are served by id (a hash of the app name),
so no file path is ever exposed to the web page.
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

_NOWIN = 0x08000000
_ID = re.compile(r"[0-9a-f]{40}")
_SCRIPT = (
    "Add-Type -AssemblyName System.Drawing; "
    "$items = Get-Content -Raw -LiteralPath $env:DW_IN | ConvertFrom-Json; "
    "foreach ($i in $items) { try { "
    "$ic = [System.Drawing.Icon]::ExtractAssociatedIcon($i.path); "
    "if ($ic) { $b = $ic.ToBitmap(); $b.Save((Join-Path $env:DW_OUT ($i.id + '.png')), [System.Drawing.Imaging.ImageFormat]::Png); "
    "$b.Dispose(); $ic.Dispose() } } catch {} }"
)
_listing = {"t": 0.0, "ids": []}


def app_id(label: str) -> str:
    return hashlib.sha1(label.encode("utf-8")).hexdigest()


def is_valid_id(s: str) -> bool:
    return bool(_ID.fullmatch(s or ""))


def icon_dir(home) -> Path:
    d = Path(home) / "icons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _device_map() -> dict:
    """{'\\\\device\\\\harddiskvolume6': 'C:'} from the drive letters Windows has assigned."""
    out = {}
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if ctypes.windll.kernel32.QueryDosDeviceW(f"{letter}:", buf, 1024):
                out[buf.value.lower()] = f"{letter}:"
    except Exception:
        pass
    return out


def to_win_path(nt_path: str, devmap=None):
    """'\\device\\harddiskvolume6\\program files\\x.exe' -> 'C:\\program files\\x.exe' (None if it can't be mapped)."""
    p = nt_path.strip().rstrip("\x00")
    low = p.lower()
    for dev, letter in (devmap if devmap is not None else _device_map()).items():
        if low.startswith(dev + "\\"):
            return letter + p[len(dev):]
    return p if re.match(r"^[A-Za-z]:\\", p) else None


def available(home) -> list:
    """Ids that have an icon file (cached for 10 s because the UI asks every 2 s)."""
    if time.time() - _listing["t"] > 10:
        try:
            _listing["ids"] = [f.stem for f in icon_dir(home).glob("*.png") if _ID.fullmatch(f.stem)]
        except OSError:
            _listing["ids"] = []
        _listing["t"] = time.time()
    return _listing["ids"]


def read_icon(home, icon_id: str):
    if not is_valid_id(icon_id):
        return None
    try:
        return (icon_dir(home) / f"{icon_id}.png").read_bytes()
    except OSError:
        return None


def extract(paths: dict, home, limit=80) -> int:
    """paths: {app label: raw NT path from SRUM}. Extracts icons that are not cached yet. Returns how many were tried."""
    d = icon_dir(home)
    devmap = _device_map()
    items = []
    for label, raw in paths.items():
        if len(items) >= limit:
            break
        iid = app_id(label)
        if (d / f"{iid}.png").exists():
            continue
        win = to_win_path(raw, devmap)
        if win and win.lower().endswith(".exe") and os.path.isfile(win):
            items.append({"id": iid, "path": win})
    if not items:
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(items, f)
        tmp = f.name
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", _SCRIPT],
                       env=dict(os.environ, DW_IN=tmp, DW_OUT=str(d)), capture_output=True, timeout=120, creationflags=_NOWIN)
    except (OSError, subprocess.SubprocessError):
        pass
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    _listing["t"] = 0.0
    return len(items)
