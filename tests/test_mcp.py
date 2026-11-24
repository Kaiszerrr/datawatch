import json
import subprocess
import sys

import pytest

from datawatch import config, mcp_server as m
from datawatch.store import UsageStore


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAWATCH_HOME", str(tmp_path))
    return m.Context(home=tmp_path)


def call(ctx_, method, params=None, i=1):
    return m.handle({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}}, ctx_)


def text(resp):
    return json.loads(resp["result"]["content"][0]["text"])


def test_initialize_and_tools_list_read_only(ctx):
    r = call(ctx, "initialize", {"protocolVersion": "2025-03-26"})
    assert r["result"]["protocolVersion"] == "2025-03-26" and r["result"]["serverInfo"]["name"] == "datawatch"
    names = {t["name"] for t in call(ctx, "tools/list")["result"]["tools"]}
    assert names == {"get_usage_summary", "get_app_usage", "get_limits"}


def test_unknown_protocol_version_falls_back(ctx):
    assert call(ctx, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"] == m.PROTOCOL_VERSIONS[0]


def test_notification_gets_no_reply(ctx):
    assert m.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, ctx) is None


def test_bad_requests(ctx):
    assert m.handle("nope", ctx)["error"]["code"] == -32600
    assert m.handle({"jsonrpc": "1.0", "id": 1, "method": "x"}, ctx)["error"]["code"] == -32600
    assert call(ctx, "does/not/exist")["error"]["code"] == -32601
    assert call(ctx, "tools/call", {"name": "rm_rf"})["error"]["code"] == -32602
    assert call(ctx, "tools/call", {})["error"]["code"] == -32602


def test_usage_summary(ctx, tmp_path):
    import time
    s = UsageStore(tmp_path / "usage.json")
    s.add_sample({"E": (0, 0)}); s.add_sample({"E": (2_000_000_000, 500_000_000)}); s.save()
    d = text(call(ctx, "tools/call", {"name": "get_usage_summary"}))
    assert d["today_gb"]["download"] == 2.0 and d["today_gb"]["total"] == 2.5
    assert d["daily_used_percent"] == 50.0 and len(d["last_14_days_gb"]) == 14
    assert "C:" not in json.dumps(d) and "Users" not in json.dumps(d)


def test_app_usage_without_data_and_with_data(ctx, tmp_path):
    d = text(call(ctx, "tools/call", {"name": "get_app_usage"}))
    assert d["available"] is False
    import time
    today = time.strftime("%Y-%m-%d")
    (tmp_path / "srum_cache.json").write_text(json.dumps({"days": {today: {"a.exe": [3_000_000, 1_000_000], "b\x07.exe": [1, 1]}}, "made": time.time()}), encoding="utf-8")
    d = text(call(ctx, "tools/call", {"name": "get_app_usage", "arguments": {"range": "today", "limit": 1}}))
    assert d["available"] and d["apps"][0]["app"] == "a.exe" and d["apps"][0]["total_mb"] == 4.0 and len(d["apps"]) == 1
    d2 = text(call(ctx, "tools/call", {"name": "get_app_usage"}))
    assert all("\x07" not in a["app"] for a in d2["apps"])                      # control characters stripped
    bad = call(ctx, "tools/call", {"name": "get_app_usage", "arguments": {"range": "year"}})
    assert bad["result"]["isError"] is True


def test_set_limits_is_blocked_without_flag(ctx):
    r = call(ctx, "tools/call", {"name": "set_limits", "arguments": {"daily_limit_gb": 99}})
    assert r["result"]["isError"] is True and config.load()["daily_limit_gb"] == 5.0


def test_set_limits_with_flag_validates(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAWATCH_HOME", str(tmp_path))
    c = m.Context(home=tmp_path, allow_write=True)
    assert "set_limits" in {t["name"] for t in call(c, "tools/list")["result"]["tools"]}
    ok = text(call(c, "tools/call", {"name": "set_limits", "arguments": {"daily_limit_gb": 3, "unknown": "x"}}))
    assert ok["daily_limit_gb"] == 3.0 and config.load()["daily_limit_gb"] == 3.0 and "unknown" not in ok
    assert call(c, "tools/call", {"name": "set_limits", "arguments": {"daily_limit_gb": -1}})["result"]["isError"] is True
    assert call(c, "tools/call", {"name": "set_limits", "arguments": {"warn_percents": [100]}})["result"]["isError"] is True
    assert config.load()["daily_limit_gb"] == 3.0                                 # bad calls changed nothing


def test_stdio_end_to_end(tmp_path):
    env = {"DATAWATCH_HOME": str(tmp_path), "SYSTEMROOT": "C:/Windows"}
    reqs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    p = subprocess.run([sys.executable, "-m", "datawatch.mcp_server"], input="\n".join(json.dumps(r) for r in reqs) + "\nnot json\n",
                       capture_output=True, text=True, env=env, timeout=30)
    lines = [json.loads(x) for x in p.stdout.splitlines()]
    assert [x.get("id") for x in lines] == [1, 2, None] and lines[2]["error"]["code"] == -32700
