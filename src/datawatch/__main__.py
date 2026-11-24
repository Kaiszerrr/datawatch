"""datawatch: run the monitor and open the dashboard.

  datawatch              start (or just open the dashboard if it is already running)
  datawatch --background start without opening the browser (used by 'start with Windows')
  datawatch --port 8777  use another local port
  datawatch mcp          connect an AI assistant (MCP over stdio); add --allow-write to let it change limits
"""
import argparse
import sys
import threading
import webbrowser

from .app import App
from .server import serve

DEFAULT_PORT = 8777


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "mcp":                       # `datawatch mcp [--allow-write]`: let an AI assistant read the numbers
        from .mcp_server import main as mcp_main
        return mcp_main(raw[1:])
    ap = argparse.ArgumentParser(prog="datawatch", description="Data usage monitor with limits (Windows).")
    ap.add_argument("--background", action="store_true", help="do not open the browser")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        ap.error("port must be 1024-65535")
    url = f"http://127.0.0.1:{args.port}/"
    app = App()
    try:
        srv = serve(app, args.port)
    except OSError:                                   # port taken: datawatch is already running, just show it
        if not args.background:
            webbrowser.open(url)
        return 0
    threading.Thread(target=app.run, daemon=True).start()
    if not args.background:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    finally:
        app.stop.set()
        try:
            app.persist()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
