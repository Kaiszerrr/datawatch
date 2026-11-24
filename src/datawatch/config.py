"""Settings: defaults, validation and storage in %APPDATA%/datawatch (override with DATAWATCH_HOME)."""
import json
import os
import re
from pathlib import Path

DEFAULTS = {
    "daily_limit_gb": 5.0,        # whole PC, download + upload; 0 = off
    "monthly_limit_gb": 0.0,      # 0 = off
    "warn_percents": [50, 80],    # alerts before the limit itself (100%)
    "app_limits_mb": {},          # {"chrome.exe": 2000}: per-app daily limits (needs per-app data)
    "exclude_adapters": [],       # extra adapter names to ignore
}
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def home() -> Path:
    base = os.environ.get("DATAWATCH_HOME") or os.path.join(os.environ.get("APPDATA", str(Path.home())), "datawatch")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _num(v, name, hi):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not 0 <= float(v) <= hi:
        raise ValueError(f"{name} out of range")
    return float(v)


def _name(s, what):
    if not isinstance(s, str) or not s.strip() or len(s) > 100 or _CTRL.search(s):
        raise ValueError(f"bad {what}")
    return s.strip()


def validate(d) -> dict:
    """Return a clean settings dict or raise ValueError. Unknown keys are ignored, never stored."""
    if not isinstance(d, dict):
        raise ValueError("settings must be an object")
    out = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    if "daily_limit_gb" in d:
        out["daily_limit_gb"] = _num(d["daily_limit_gb"], "daily_limit_gb", 100000)
    if "monthly_limit_gb" in d:
        out["monthly_limit_gb"] = _num(d["monthly_limit_gb"], "monthly_limit_gb", 1000000)
    if "warn_percents" in d:
        w = d["warn_percents"]
        if not isinstance(w, list) or len(w) > 5 or any(isinstance(x, bool) or not isinstance(x, int) or not 1 <= x <= 99 for x in w):
            raise ValueError("warn_percents must be up to 5 whole numbers from 1 to 99")
        out["warn_percents"] = sorted(set(w))
    if "app_limits_mb" in d:
        a = d["app_limits_mb"]
        if not isinstance(a, dict) or len(a) > 50:
            raise ValueError("app_limits_mb must be an object with at most 50 apps")
        out["app_limits_mb"] = {_name(k, "app name").lower(): _num(v, "app limit", 10_000_000) for k, v in a.items()}
    if "exclude_adapters" in d:
        e = d["exclude_adapters"]
        if not isinstance(e, list) or len(e) > 20:
            raise ValueError("exclude_adapters must be a list of at most 20 names")
        out["exclude_adapters"] = [_name(x, "adapter name") for x in e]
    return out


def load() -> dict:
    try:
        return validate(json.loads((home() / "settings.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return validate({})


def save(settings: dict) -> None:
    p = home() / "settings.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(validate(settings), indent=1), encoding="utf-8")
    os.replace(tmp, p)
