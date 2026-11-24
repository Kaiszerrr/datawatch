"""Limit checks: which alerts are due right now. Pure logic (no I/O), so it is easy to test."""
import time

GB = 1e9
MB = 1e6


def _fmt(b):
    return f"{b / GB:.2f} GB" if b >= GB else f"{b / MB:.0f} MB"


def due_alerts(settings: dict, today_bytes: float, month_bytes: float, app_today: dict | None, now=None) -> list:
    """Return [(key, title, text)] for every threshold currently crossed. The caller de-duplicates by key+day."""
    now = time.time() if now is None else now
    out = []
    levels = sorted(set(settings.get("warn_percents", []))) + [100]

    def add_levels(prefix, label, used, limit):
        if limit <= 0:
            return
        for pct in levels:
            if used >= limit * pct / 100:
                key = f"{prefix}:{pct}"
                if pct >= 100:
                    out.append((key, f"{label} limit reached", f"{_fmt(used)} used of {_fmt(limit)}."))
                else:
                    out.append((key, f"{label}: {pct}% used", f"{_fmt(used)} of {_fmt(limit)}."))

    add_levels("daily", "Daily data", today_bytes, settings.get("daily_limit_gb", 0) * GB)
    add_levels("monthly", "Monthly data", month_bytes, settings.get("monthly_limit_gb", 0) * GB)
    for app, mb in (settings.get("app_limits_mb") or {}).items():
        add_levels(f"app:{app}", app, (app_today or {}).get(app, 0), mb * MB)
    # only keep the highest level crossed per series, so a jump past 80% and 100% sends one alert, not two
    best = {}
    for key, title, text in out:
        series, pct = key.rsplit(":", 1)
        if series not in best or int(pct) > int(best[series][0].rsplit(":", 1)[1]):
            best[series] = (key, title, text)
    return list(best.values())
