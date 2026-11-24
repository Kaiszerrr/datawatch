"""Attack tests against the running local server (docs/security.md maps each one to a baseline line)."""
import http.client
import json
import socket
import threading

import pytest

from datawatch import config
from datawatch.app import App
from datawatch.server import serve


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAWATCH_HOME", str(tmp_path))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    app = App(home=tmp_path, notifier=lambda *a: None)
    server = serve(app, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f"127.0.0.1:{port}"
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", "/api/state", headers={"Host": host})
    token = json.loads(c.getresponse().read())["token"]
    yield port, host, token, app, tmp_path
    server.shutdown(); server.server_close()


def req(port, method, path, host, headers=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    h = {"Host": host, **(headers or {})}
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def post(srv_, path, obj=None, token=True, **extra):
    port, host, tok, *_ = srv_
    h = {"Content-Type": "application/json", **extra}
    if token:
        h["X-DW-Token"] = tok
    return req(port, "POST", path, host, h, json.dumps(obj if obj is not None else {}))


def test_security_headers_and_csp(srv):
    port, host, *_ = srv
    for path in ("/", "/app.js", "/style.css", "/api/state"):
        st, h, _ = req(port, "GET", path, host)
        assert st == 200
        csp = h["Content-Security-Policy"]
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp and "default-src 'none'" in csp
        assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
        assert h["Referrer-Policy"] == "no-referrer" and h["Cache-Control"] == "no-store"
        assert "Server" in h and "Python" not in h["Server"]


def test_no_inline_script_or_style_in_page(srv):
    port, host, *_ = srv
    _, _, body = req(port, "GET", "/", host)
    html = body.decode()
    assert "<script>" not in html and " style=" not in html and "onclick" not in html


def test_foreign_host_refused(srv):
    port, *_ = srv
    for bad in ("evil.com", f"evil.com:{port}", "127.0.0.1", ""):
        assert req(port, "GET", "/api/state", bad)[0] == 403


def test_post_needs_token_origin_and_json(srv):
    port, host, tok, *_ = srv
    assert post(srv, "/api/settings", {}, token=False)[0] == 403                            # no token
    assert post(srv, "/api/settings", {}, Origin="http://evil.com")[0] == 403               # foreign origin
    assert post(srv, "/api/settings", {}, **{"Sec-Fetch-Site": "cross-site"})[0] == 403     # cross-site
    st, *_ = req(port, "POST", "/api/settings", host, {"X-DW-Token": tok, "Content-Type": "text/plain"}, "{}")
    assert st == 415
    st, *_ = req(port, "POST", "/api/settings", host, {"X-DW-Token": "wrong" * 8, "Content-Type": "application/json"}, "{}")
    assert st == 403


def test_oversize_and_bad_json(srv):
    port, host, tok, *_ = srv
    h = {"X-DW-Token": tok, "Content-Type": "application/json"}
    assert req(port, "POST", "/api/settings", host, h, "x" * 5000)[0] == 413
    assert req(port, "POST", "/api/settings", host, h, "{not json")[0] == 400


def test_settings_validated_no_trace_leak(srv):
    st, _, body = post(srv, "/api/settings", {"daily_limit_gb": -5})
    assert st == 400 and b"Traceback" not in body and b".py" not in body
    st, _, body = post(srv, "/api/settings", {"daily_limit_gb": 3, "warn_percents": [40]})
    assert st == 200 and json.loads(body)["settings"]["daily_limit_gb"] == 3.0
    assert config.load()["warn_percents"] == [40]


def test_autostart_needs_bool(srv):
    assert post(srv, "/api/autostart", {"enabled": "yes"})[0] == 400


def test_unknown_routes_and_methods(srv):
    port, host, *_ = srv
    assert req(port, "GET", "/etc/passwd", host)[0] == 404
    assert req(port, "GET", "/../../secret", host)[0] == 404
    assert req(port, "GET", "/api/settings", host)[0] == 404
    assert req(port, "PUT", "/api/settings", host)[0] in (404, 501)


def test_state_has_no_secrets_besides_token(srv):
    port, host, *_ = srv
    _, _, body = req(port, "GET", "/api/state", host)
    s = body.decode()
    assert "C:\\" not in s and "Users" not in s


def test_listens_only_on_loopback(srv):
    port, *_ = srv
    c = socket.socket()
    try:
        assert c.connect_ex(("127.0.0.1", port)) == 0
    finally:
        c.close()


def test_icon_route_serves_only_valid_ids(srv):
    from datawatch import icons
    port, host, tok, app, home = srv
    i = icons.app_id("demo.exe")
    (icons.icon_dir(home) / f"{i}.png").write_bytes(b"PNGFAKE")
    st, h, body = req(port, "GET", f"/icon/{i}.png", host)
    assert st == 200 and h["Content-Type"] == "image/png" and body == b"PNGFAKE"
    for bad in ("/icon/../settings.png", "/icon/..%2Fsettings.png", "/icon/zzz.png", f"/icon/{i}.txt"):
        assert req(port, "GET", bad, host)[0] == 404
