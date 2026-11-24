import time

import pytest

from datawatch import config, limits, srum
from datawatch.store import UsageStore


# ---------------- config / validation
def test_defaults_valid():
    s = config.validate({})
    assert s["daily_limit_gb"] == 5.0 and s["warn_percents"] == [50, 80]


@pytest.mark.parametrize("bad", [
    {"daily_limit_gb": -1}, {"daily_limit_gb": "5"}, {"daily_limit_gb": True}, {"daily_limit_gb": 1e9},
    {"warn_percents": [0]}, {"warn_percents": [100]}, {"warn_percents": [1.5]}, {"warn_percents": list(range(1, 9))},
    {"app_limits_mb": {"": 5}}, {"app_limits_mb": {"a" * 101: 5}}, {"app_limits_mb": {"x\n": 5}}, {"app_limits_mb": {"x": -1}},
    {"app_limits_mb": [1]}, {"exclude_adapters": ["a"] * 21}, {"exclude_adapters": [5]}, "nope", None,
])
def test_validate_rejects(bad):
    with pytest.raises(ValueError):
        config.validate(bad)


def test_validate_ignores_unknown_keys_and_lowercases_apps():
    s = config.validate({"evil": "x", "app_limits_mb": {"Chrome.EXE": 500}})
    assert "evil" not in s and s["app_limits_mb"] == {"chrome.exe": 500.0}


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAWATCH_HOME", str(tmp_path))
    config.save({"daily_limit_gb": 3})
    assert config.load()["daily_limit_gb"] == 3.0
    (tmp_path / "settings.json").write_text("{broken", encoding="utf-8")
    assert config.load()["daily_limit_gb"] == 5.0          # corrupt file falls back to defaults


# ---------------- store
def T(h=12, d=24):
    return time.mktime((2026, 11, d, h, 0, 0, 0, 0, -1))


def test_store_counts_deltas_and_hours(tmp_path):
    s = UsageStore(tmp_path / "u.json")
    s.add_sample({"Eth": (1000, 500)}, T())             # first sight: baseline only
    assert s.day("2026-11-24") == {"down": 0, "up": 0}
    s.add_sample({"Eth": (4000, 1500)}, T())
    d = s.day("2026-11-24")
    assert (d["down"], d["up"]) == (3000, 1000)
    assert d["hours"]["12"] == [3000, 1000]


def test_store_counter_reset_counts_everything_since_boot(tmp_path):
    s = UsageStore(tmp_path / "u.json")
    s.add_sample({"Eth": (10_000, 10_000)}, T())
    s.add_sample({"Eth": (700, 300)}, T())              # reboot: counters restarted
    assert (s.day("2026-11-24")["down"], s.day("2026-11-24")["up"]) == (700, 300)


def test_store_new_adapter_not_counted_first_time(tmp_path):
    s = UsageStore(tmp_path / "u.json")
    s.add_sample({"Eth": (0, 0)}, T())
    s.add_sample({"Eth": (100, 0), "WiFi": (9_999_999, 9_999_999)}, T())
    assert s.day("2026-11-24")["down"] == 100


def test_store_persists_and_month_total(tmp_path):
    s = UsageStore(tmp_path / "u.json")
    s.add_sample({"E": (0, 0)}, T(d=23)); s.add_sample({"E": (100, 50)}, T(d=23))
    s.add_sample({"E": (300, 150)}, T(d=24))
    s.save()
    s2 = UsageStore(tmp_path / "u.json")
    assert s2.month_total("2026-11") == 450 and s2.day("2026-11-23")["down"] == 100


def test_alert_dedupe(tmp_path):
    s = UsageStore(tmp_path / "u.json")
    assert s.mark_alert("daily:80", "2026-11-24") is True
    assert s.mark_alert("daily:80", "2026-11-24") is False
    assert s.mark_alert("daily:80", "2026-11-25") is True


# ---------------- limits
BASE = {"daily_limit_gb": 5, "monthly_limit_gb": 0, "warn_percents": [50, 80], "app_limits_mb": {}}


def keys(a):
    return sorted(k for k, _, _ in a)


def test_no_alert_under_threshold():
    assert limits.due_alerts(BASE, 1e9, 0, {}) == []


def test_warn_then_limit():
    assert keys(limits.due_alerts(BASE, 2.6e9, 0, {})) == ["daily:50"]
    assert keys(limits.due_alerts(BASE, 4.2e9, 0, {})) == ["daily:80"]
    assert keys(limits.due_alerts(BASE, 5.1e9, 0, {})) == ["daily:100"]


def test_off_when_zero():
    assert limits.due_alerts(dict(BASE, daily_limit_gb=0), 99e9, 0, {}) == []


def test_monthly_and_app():
    s = dict(BASE, monthly_limit_gb=100, app_limits_mb={"chrome.exe": 1000})
    got = keys(limits.due_alerts(s, 0, 101e9, {"chrome.exe": 1.2e9}))
    assert got == ["app:chrome.exe:100", "monthly:100"]


# ---------------- srum helpers
@pytest.mark.parametrize("raw,want", [
    (r"\device\harddiskvolume6\program files\google\chrome\application\chrome.exe", "chrome.exe"),
    ("Microsoft.GamingServices_38.118.9001.0_x64__8wekyb3d8bbwe", "microsoft.gamingservices"),
    ("DoSvc", "dosvc"), (None, srum.UNKNOWN), ("", srum.UNKNOWN), ("   ", srum.UNKNOWN),
])
def test_app_label(raw, want):
    assert srum.app_label(raw) == want


def test_top_apps_and_ranges():
    days = {"2026-11-24": {"a.exe": [100, 50], "b.exe": [10, 0]}, "2026-11-10": {"a.exe": [1000, 0]}}
    rows = srum.top_apps(days, "2026-11-20")
    assert [(r["app"], r["down"], r["up"]) for r in rows] == [("a.exe", 100, 50), ("b.exe", 10, 0)]
    assert all(len(r["id"]) == 40 for r in rows)
    assert srum.top_apps(days, "0000")[0]["app"] == "a.exe"


def test_snapshot_rejects_unsafe_path(tmp_path):
    with pytest.raises(ValueError):
        srum.snapshot(tmp_path / "a;b.dat")


def test_srum_ts_decoding():
    import struct
    bits = struct.unpack("<q", struct.pack("<d", 46000.5))[0]
    assert srum._ts(bits).year == 2025 or srum._ts(bits).year >= 2025
    assert srum._ts(None) is None


# ---------------- icons
BS = chr(92)
FAKE_PNG = b"PNGFAKE"


def test_icon_ids_and_paths():
    from datawatch import icons
    i = icons.app_id("chrome.exe")
    assert icons.is_valid_id(i) and i == icons.app_id("chrome.exe") and i != icons.app_id("brave.exe")
    for bad in ("", "../x", "A" * 40, "g" * 40, i + "0", i[:-1], None):
        assert not icons.is_valid_id(bad)


def test_nt_path_mapping():
    from datawatch import icons
    dev = {BS + "device" + BS + "harddiskvolume6": "C:"}
    nt = BS.join(["", "device", "harddiskvolume6", "program files", "x", "a.exe"])
    assert icons.to_win_path(nt, dev) == BS.join(["C:", "program files", "x", "a.exe"])
    assert icons.to_win_path(BS.join(["", "Device", "HarddiskVolume6", "a.exe"]), dev) == "C:" + BS + "a.exe"
    assert icons.to_win_path(BS.join(["", "device", "harddiskvolume9", "a.exe"]), dev) is None
    assert icons.to_win_path("DoSvc", dev) is None


def test_read_icon_only_by_valid_id(tmp_path):
    from datawatch import icons
    i = icons.app_id("x.exe")
    (icons.icon_dir(tmp_path) / f"{i}.png").write_bytes(FAKE_PNG)
    assert icons.read_icon(tmp_path, i) == FAKE_PNG
    assert icons.read_icon(tmp_path, "../../settings") is None
    assert icons.read_icon(tmp_path, icons.app_id("missing.exe")) is None


def test_extract_skips_non_exe_and_missing(tmp_path):
    from datawatch import icons
    missing = BS.join(["C:", "definitely", "missing", "x.exe"])
    assert icons.extract({"svc": "dosvc", "x": missing}, tmp_path) == 0
