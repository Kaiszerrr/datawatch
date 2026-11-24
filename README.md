# datawatch

See where your internet data goes, and get warned before you run out. A small Windows app with a live dashboard.

- **Live:** today's download and upload, current speed, usage by hour and for the last 14 days.
- **Per app:** which programs used the data (from Windows' own usage history, about the last 30-60 days).
- **Limits:** a daily limit, a monthly limit and per-app daily limits. You get a Windows notification at the
  warning levels you choose and when a limit is reached. datawatch only alerts: it never blocks or changes anything.
- **Private:** everything stays on your PC. No account, no cloud, no tracking, no outside requests.

## Install (no Python needed)

1. Download `datawatch.exe` from the [Releases](../../releases) page.
2. Double-click it. Your browser opens the dashboard at `http://127.0.0.1:8777`.
3. Open the **Limits** tab to set your limits. Tick "Start datawatch with Windows" to keep it counting.

Windows SmartScreen may warn about an unsigned app the first time: choose *More info > Run anyway*, or build it
yourself (below). The release page lists the SHA-256 of each file.

## Run from source

```powershell
git clone <this repo>
cd datawatch
python -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\datawatch
```

## Per-app data needs one admin approval

Windows keeps per-app network history in a protected database. On the **Apps** tab press *Load / refresh per-app
data*: Windows asks for administrator permission once per refresh, datawatch copies the database, reads it, deletes
the copy and keeps only the totals per app and day. Without it you still get the live totals and limits for the
whole PC.

## How the numbers work

- The total comes from the byte counters of your real network adapters (Ethernet, Wi-Fi). VPN and virtual adapters
  are skipped so traffic is not counted twice. Everything on the PC counts, not just one app.
- Counting starts when datawatch first runs. While it is closed nothing is recorded; the next time it runs it adds
  what was moved since it last looked (unless the PC rebooted in between).
- Per-app numbers come from Windows (SRUM) and are updated by Windows about once an hour.

## Settings and data

`%APPDATA%\datawatch\` holds `settings.json`, `usage.json` and `srum_cache.json`. Set `DATAWATCH_HOME` to move it.
Use `datawatch --port 9000` for another port, `datawatch --background` to start without opening the browser.

## Build the .exe

```powershell
.venv\Scripts\pip install -e ".[dev]"
.\build.ps1          # -> dist\datawatch.exe
```

Tagging a release (`git tag v0.1.0 && git push --tags`) builds and publishes it with GitHub Actions.

## Develop

```powershell
.venv\Scripts\pytest
```

Security notes and test proof: [docs/security.md](docs/security.md). Windows only (uses Windows APIs for counters,
notifications and the usage history). MIT licensed.
