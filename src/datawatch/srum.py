"""Per-app network usage from Windows' own history database (SRUM, C:/Windows/System32/sru/SRUDB.dat).

Windows records bytes sent/received per app roughly hourly and keeps about 30-60 days. The file is locked and
protected, so a copy is taken with `esentutl /y ... /vss`, which needs Administrator rights. datawatch asks for
that only when you press the button; it then reads the copy as a normal user. Nothing leaves your PC.
"""
import json
import os
import re
import struct
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

SRUM_SOURCE = r"C:\Windows\System32\sru\SRUDB.dat"
NET_TABLE = "{973F5D5C-1D90-4944-BE8E-24B94231A174}"
UNKNOWN = "(system / unknown)"
_NOWIN = 0x08000000


def app_label(raw) -> str:
    """Short, readable app name from an SRUM app id (an NT path, a package name or a service name)."""
    if not raw:
        return UNKNOWN
    s = str(raw).strip().rstrip("\x00")
    if not s:
        return UNKNOWN
    if "\\" in s:
        s = s.rsplit("\\", 1)[-1]
    if re.fullmatch(r"[\w.\-]+_[\d.]+_\w+__\w+", s):      # UWP package: Name_version_arch__publisher -> Name
        s = s.split("_", 1)[0]
    return s[:100].lower()


def _ts(v):
    """SRUM timestamps are OLE dates; some readers hand back the raw 8 bytes as an int."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, int):
        v = struct.unpack("<d", struct.pack("<q", v))[0]
    if isinstance(v, float):
        return datetime(1899, 12, 30) + timedelta(days=v)
    return None


def parse(path) -> dict:
    """Read a copy of SRUDB.dat. Returns {'days': {'YYYY-MM-DD': {app: [down, up]}}, 'made': unix time}."""
    from dissect.esedb import EseDB
    with open(path, "rb") as fh:
        db = EseDB(fh)
        names = {}
        for r in db.table("SruDbIdMapTable").records():
            blob, kind = r.get("IdBlob"), r.get("IdType")
            if isinstance(blob, bytes):
                names[r.get("IdIndex")] = "" if kind == 3 else blob.decode("utf-16-le", "ignore")
            else:
                names[r.get("IdIndex")] = str(blob or "")
        days = {}
        for r in db.table(NET_TABLE).records():
            t = _ts(r.get("TimeStamp"))
            if t is None:
                continue
            local = t.replace(tzinfo=None) + (datetime.now() - datetime.utcnow())      # SRUM stores UTC
            app = app_label(names.get(r.get("AppId")))
            cell = days.setdefault(local.strftime("%Y-%m-%d"), {}).setdefault(app, [0, 0])
            cell[0] += int(r.get("BytesRecvd") or 0)
            cell[1] += int(r.get("BytesSent") or 0)
    return {"days": days, "made": time.time()}


def top_apps(days: dict, since_day: str, limit=60) -> list:
    """Sum per app from `since_day` on. Returns [{'app', 'down', 'up'}] sorted by total."""
    agg = {}
    for d, apps in days.items():
        if d >= since_day:
            for app, (down, up) in apps.items():
                a = agg.setdefault(app, [0, 0])
                a[0] += down
                a[1] += up
    rows = [{"app": k, "down": v[0], "up": v[1]} for k, v in agg.items()]
    rows.sort(key=lambda r: -(r["down"] + r["up"]))
    return rows[:limit]


def today_by_app(days: dict) -> dict:
    return {app: v[0] + v[1] for app, v in days.get(time.strftime("%Y-%m-%d"), {}).items()}


def is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def snapshot(dest: Path, timeout=120) -> bool:
    """Copy SRUDB.dat to `dest` with esentutl + VSS. Elevates (UAC prompt) unless already admin. True on success."""
    dest = Path(dest)
    if re.search(r'["\'`$;&|<>]', str(dest)):
        raise ValueError("unsafe destination path")
    dest.unlink(missing_ok=True)
    if is_admin():
        cmd = ["esentutl.exe", "/y", SRUM_SOURCE, "/vss", "/d", str(dest)]
    else:
        ps = ("Start-Process -FilePath esentutl.exe -Verb RunAs -WindowStyle Hidden -Wait -ArgumentList "
              f"'/y','{SRUM_SOURCE}','/vss','/d','{dest}'")
        cmd = ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps]
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=_NOWIN)
    except (OSError, subprocess.SubprocessError):
        return False
    return dest.exists() and dest.stat().st_size > 0


def refresh(home: Path) -> dict:
    """Snapshot + parse + cache. Returns the parsed result, or raises RuntimeError with a plain-language reason."""
    copy = Path(home) / "srudb_copy.dat"
    if not snapshot(copy):
        raise RuntimeError("Windows did not give access to its usage history (the admin prompt was declined or failed).")
    try:
        result = parse(copy)
    except Exception as e:
        raise RuntimeError("Could not read the usage history file.") from e
    finally:
        copy.unlink(missing_ok=True)                       # the copy holds data about every app: don't leave it lying around
    tmp = Path(home) / "srum_cache.tmp"
    tmp.write_text(json.dumps(result), encoding="utf-8")
    os.replace(tmp, Path(home) / "srum_cache.json")
    return result


def load_cache(home: Path):
    try:
        return json.loads((Path(home) / "srum_cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
