"""Usage store: per-day / per-hour byte totals built from cumulative adapter counters."""
import json
import os
import threading
import time
from pathlib import Path

KEEP_DAYS = 400


class UsageStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("days", {})
        self.data.setdefault("last", {})
        self.data.setdefault("alerted", {})

    # ---- writing
    def add_sample(self, counters: dict, now=None) -> None:
        """counters: {adapter: (rx_bytes, tx_bytes)} cumulative since boot. Adds the change since the last sample."""
        now = time.time() if now is None else now
        lt = time.localtime(now)
        with self.lock:
            day = self.data["days"].setdefault(time.strftime("%Y-%m-%d", lt), {"down": 0, "up": 0})
            for name, (rx, tx) in counters.items():
                prev = self.data["last"].get(name)
                if prev is not None:                       # first sight of an adapter: start counting from now
                    drx, dtx = rx - prev[0], tx - prev[1]
                    if drx < 0 or dtx < 0:                 # counters reset (reboot / adapter reset): all of it is new
                        drx, dtx = rx, tx
                    day["down"] += drx
                    day["up"] += dtx
                    h = day.setdefault("hours", {}).setdefault(str(lt.tm_hour), [0, 0])
                    h[0] += drx
                    h[1] += dtx
            self.data["last"] = {k: [v[0], v[1]] for k, v in counters.items()}

    def mark_alert(self, key: str, day: str) -> bool:
        """True the first time `key` is raised for `day`."""
        with self.lock:
            seen = self.data["alerted"].setdefault(day, [])
            if key in seen:
                return False
            seen.append(key)
            return True

    def save(self) -> None:
        with self.lock:
            days = dict(sorted(self.data["days"].items())[-KEEP_DAYS:])
            self.data["days"] = days
            keep = set(days) | {d[:7] for d in days}
            self.data["alerted"] = {k: v for k, v in self.data["alerted"].items() if k in keep}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data), encoding="utf-8")
            os.replace(tmp, self.path)

    # ---- reading
    def day(self, date: str) -> dict:
        with self.lock:
            return dict(self.data["days"].get(date, {"down": 0, "up": 0}))

    def today(self) -> dict:
        return self.day(time.strftime("%Y-%m-%d"))

    def month_total(self, ym=None) -> int:
        ym = ym or time.strftime("%Y-%m")
        with self.lock:
            return sum(v["down"] + v["up"] for d, v in self.data["days"].items() if d.startswith(ym))

    def recent_days(self, n: int, now=None) -> list:
        now = time.time() if now is None else now
        out = []
        for i in range(n - 1, -1, -1):
            d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            v = self.day(d)
            out.append({"day": d, "down": v["down"], "up": v["up"]})
        return out

    def hours_today(self) -> list:
        hours = [[0, 0] for _ in range(24)]
        for h, v in (self.today().get("hours") or {}).items():
            if h.isdigit() and 0 <= int(h) < 24:
                hours[int(h)] = list(v)
        return hours
