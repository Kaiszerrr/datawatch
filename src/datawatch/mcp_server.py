"""MCP server: lets an AI assistant (Claude Desktop, Claude Code, any MCP client) read datawatch's numbers.

Runs on the SAME PC as the person's datawatch, over stdio. There is no account, key or network connection: the
assistant starts this program itself and talks to it through its input/output. It only reads datawatch's local files.

Tools:   get_usage_summary, get_app_usage, get_limits           (read-only, always on)
         set_limits                                              (only when started with --allow-write)
Returned data are totals only: no file paths, no user names, no PC details.
"""
import json
import re
import sys
import time
from pathlib import Path

from . import __version__, config, srum
from .store import UsageStore

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
RANGES = {"today": 0, "week": 6, "month": None, "all": None}

TOOLS = [
    {"name": "get_usage_summary", "description": "Data used today and this month (download and upload), the last 14 days, and how close that is to the configured limits.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_app_usage", "description": "Top apps by data used, from Windows' usage history (needs the person to have pressed 'Load per-app data' in datawatch).",
     "inputSchema": {"type": "object", "properties": {"range": {"type": "string", "enum": list(RANGES), "default": "today"}, "limit": {"type": "integer", "minimum": 1, "maximum": 60, "default": 15}}, "additionalProperties": False}},
    {"name": "get_limits", "description": "The configured daily, monthly and per-app limits and warning percentages.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]
WRITE_TOOLS = [
    {"name": "set_limits", "description": "Change limits. Only the fields you pass change. daily_limit_gb / monthly_limit_gb (0 = off), warn_percents (whole numbers 1-99), app_limits_mb ({app: MB per day}).",
     "inputSchema": {"type": "object", "properties": {"daily_limit_gb": {"type": "number", "minimum": 0}, "monthly_limit_gb": {"type": "number", "minimum": 0},
                                                      "warn_percents": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 99}, "maxItems": 5},
                                                      "app_limits_mb": {"type": "object", "additionalProperties": {"type": "number", "minimum": 1}}}, "additionalProperties": False}},
]


def _clean(s) -> str:
    return _CTRL.sub(" ", str(s))[:100]


def _gb(b) -> float:
    return round(b / 1e9, 3)


class Context:
    def __init__(self, home=None, allow_write=False):
        self.home = Path(home) if home else config.home()
        self.allow_write = allow_write

    def tools(self):
        return TOOLS + (WRITE_TOOLS if self.allow_write else [])

    # ---- tool implementations (read local files only)
    def usage_summary(self):
        store = UsageStore(self.home / "usage.json")
        s = config.load()
        t = store.today()
        today = t["down"] + t["up"]
        cap = s["daily_limit_gb"] * 1e9
        mcap = s["monthly_limit_gb"] * 1e9
        month = store.month_total()
        return {
            "today_gb": {"download": _gb(t["down"]), "upload": _gb(t["up"]), "total": _gb(today)},
            "this_month_gb": _gb(month),
            "daily_limit_gb": s["daily_limit_gb"], "daily_used_percent": round(today / cap * 100, 1) if cap else None,
            "monthly_limit_gb": s["monthly_limit_gb"], "monthly_used_percent": round(month / mcap * 100, 1) if mcap else None,
            "last_14_days_gb": [{"day": d["day"], "total": _gb(d["down"] + d["up"])} for d in store.recent_days(14)],
            "note": "Counts all traffic on this PC's real network adapters since datawatch started recording.",
        }

    def app_usage(self, rng="today", limit=15):
        cache = srum.load_cache(self.home)
        if not cache:
            return {"available": False, "message": "No per-app data yet. Ask the person to open datawatch > Apps > Load per-app data."}
        if rng not in RANGES:
            raise ValueError("range must be one of: " + ", ".join(RANGES))
        limit = max(1, min(int(limit), 60))
        now = time.time()
        since = {"today": time.strftime("%Y-%m-%d"), "week": time.strftime("%Y-%m-%d", time.localtime(now - 6 * 86400)),
                 "month": time.strftime("%Y-%m-01"), "all": "0000-00-00"}[rng]
        rows = srum.top_apps(cache["days"], since, limit)
        return {"available": True, "range": rng, "loaded_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(cache["made"])),
                "apps": [{"app": _clean(r["app"]), "total_mb": round((r["down"] + r["up"]) / 1e6, 1), "download_mb": round(r["down"] / 1e6, 1)} for r in rows]}

    def limits(self):
        return config.load()

    def set_limits(self, args):
        if not self.allow_write:
            raise PermissionError("set_limits is disabled. The person must start the server with --allow-write.")
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
        merged = dict(config.load())
        merged.update({k: v for k, v in args.items() if k in config.DEFAULTS})
        clean = config.validate(merged)
        config.save(clean)
        return clean

    def call(self, name, args):
        args = args or {}
        if name == "get_usage_summary":
            return self.usage_summary()
        if name == "get_app_usage":
            return self.app_usage(args.get("range", "today"), args.get("limit", 15))
        if name == "get_limits":
            return self.limits()
        if name == "set_limits":
            return self.set_limits(args)
        raise KeyError(name)


def _ok(i, result):
    return {"jsonrpc": "2.0", "id": i, "result": result}


def _err(i, code, msg):
    return {"jsonrpc": "2.0", "id": i, "error": {"code": code, "message": msg}}


def handle(msg, ctx: Context):
    """One JSON-RPC message in, one response (or None for notifications) out."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _err(msg.get("id") if isinstance(msg, dict) else None, -32600, "invalid request")
    method, i, params = msg["method"], msg.get("id"), msg.get("params") or {}
    if "id" not in msg:
        return None                                              # notification (e.g. notifications/initialized)
    if method == "initialize":
        want = params.get("protocolVersion") if isinstance(params, dict) else None
        return _ok(i, {"protocolVersion": want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                       "capabilities": {"tools": {}}, "serverInfo": {"name": "datawatch", "version": __version__}})
    if method == "ping":
        return _ok(i, {})
    if method == "tools/list":
        return _ok(i, {"tools": ctx.tools()})
    if method == "tools/call":
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _err(i, -32602, "tool name required")
        if params["name"] not in {t["name"] for t in ctx.tools()} and params["name"] != "set_limits":
            return _err(i, -32602, "unknown tool")
        try:
            data = ctx.call(params["name"], params.get("arguments"))
            return _ok(i, {"content": [{"type": "text", "text": json.dumps(data, indent=1)}]})
        except (ValueError, PermissionError) as e:
            return _ok(i, {"isError": True, "content": [{"type": "text", "text": _clean(e)}]})
        except Exception:
            return _ok(i, {"isError": True, "content": [{"type": "text", "text": "internal error"}]})
    return _err(i, -32601, "method not found")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ctx = Context(allow_write="--allow-write" in argv)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            out = handle(json.loads(line), ctx)
        except ValueError:
            out = _err(None, -32700, "parse error")
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
