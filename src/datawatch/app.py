"""Application core: sampling loop, live speed, limit alerts. The HTTP layer (server.py) only reads this."""
import threading
import time

from . import autostart, config, limits, notify, sampler, srum
from .store import UsageStore


class App:
    def __init__(self, home=None, notifier=notify.send):
        self.home = home or config.home()
        self.settings = config.load()
        self.store = UsageStore(self.home / "usage.json")
        self.notifier = notifier
        self.srum = srum.load_cache(self.home)
        self.rate = []                       # [(t, down_Bps, up_Bps)]
        self.adapter = ""
        self._prev = None
        self._lock = threading.Lock()
        self._srum_busy = False
        self._srum_last = 0.0
        self.srum_error = ""
        self.stop = threading.Event()

    # ---- sampling
    def tick(self, now=None) -> None:
        """One 2-second step: live speed. Persist every ~10 s. Check limits every ~60 s."""
        now = time.time() if now is None else now
        counters = sampler.read_counters(self.settings["exclude_adapters"])
        with self._lock:
            if self._prev:
                pt, pc = self._prev
                dt = max(now - pt, 0.001)
                down = up = 0
                best = ("", -1)
                for name, (rx, tx) in counters.items():
                    p = pc.get(name)
                    if p and rx >= p[0] and tx >= p[1]:
                        d, u = rx - p[0], tx - p[1]
                        down += d
                        up += u
                        if d + u > best[1]:
                            best = (name, d + u)
                self.rate = (self.rate + [(now, down / dt, up / dt)])[-150:]
                self.adapter = best[0]
            self._prev = (now, counters)

    def persist(self, now=None) -> None:
        counters = sampler.read_counters(self.settings["exclude_adapters"])
        self.store.add_sample(counters, now)
        self.store.save()

    def check_limits(self, now=None) -> list:
        """Send each due alert once per day. Returns the alerts that were sent (for tests)."""
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        t = self.store.today()
        app_today = srum.today_by_app(self.srum["days"]) if self.srum else {}
        sent = []
        for key, title, text in limits.due_alerts(self.settings, t["down"] + t["up"], self.store.month_total(), app_today, now):
            period = today[:7] if key.startswith("monthly") else today      # monthly alerts repeat once a month, others daily
            if self.store.mark_alert(key, period):
                self.notifier(title, text)
                sent.append((key, title, text))
        if sent:
            self.store.save()
        return sent

    def run(self) -> None:
        last_save = last_check = 0.0
        while not self.stop.is_set():
            try:
                self.tick()
                now = time.time()
                if now - last_save >= 10:
                    self.persist(now)
                    last_save = now
                if now - last_check >= 60:
                    self.check_limits(now)
                    last_check = now
            except Exception:
                pass                                          # a bad sample must never kill the monitor
            self.stop.wait(2)

    # ---- settings
    def update_settings(self, new: dict) -> dict:
        clean = config.validate(new)
        config.save(clean)
        self.settings = clean
        return clean

    # ---- per-app data (SRUM)
    def refresh_apps(self) -> None:
        """Start a per-app refresh in the background (it shows a Windows admin prompt). At most one at a time."""
        with self._lock:
            if self._srum_busy or time.time() - self._srum_last < 20:
                return
            self._srum_busy = True
            self._srum_last = time.time()
            self.srum_error = ""

        def work():
            try:
                self.srum = srum.refresh(self.home)
            except RuntimeError as e:
                self.srum_error = str(e)
            finally:
                self._srum_busy = False
        threading.Thread(target=work, daemon=True).start()

    # ---- state for the UI
    def state(self) -> dict:
        t = self.store.today()
        s = self.settings
        r = self.rate[-1] if self.rate else (0, 0, 0)
        today = time.strftime("%Y-%m-%d")
        week = time.strftime("%Y-%m-%d", time.localtime(time.time() - 6 * 86400))
        month = time.strftime("%Y-%m-01")
        days = self.srum["days"] if self.srum else {}
        return {
            "today": {"down": t["down"], "up": t["up"]},
            "limits": {"daily": s["daily_limit_gb"] * 1e9, "monthly": s["monthly_limit_gb"] * 1e9},
            "month": self.store.month_total(),
            "rate": {"down": r[1], "up": r[2], "adapter": self.adapter,
                     "history": [[round(b), round(c)] for _, b, c in self.rate[-90:]]},
            "hours": self.store.hours_today(), "days": self.store.recent_days(14),
            "apps": {
                "available": self.srum is not None, "made": self.srum["made"] if self.srum else None,
                "busy": self._srum_busy, "error": self.srum_error, "admin": srum.is_admin(),
                "today": srum.top_apps(days, today), "week": srum.top_apps(days, week),
                "month": srum.top_apps(days, month), "all": srum.top_apps(days, "0000-00-00"),
            },
            "settings": s, "autostart": autostart.is_enabled(),
        }
