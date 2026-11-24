# Security notes and proof

datawatch is a local app: a Python process that serves a dashboard on `127.0.0.1` only. It has no accounts, no
database server, no cloud and makes no outside requests. This follows the project's website security baseline;
sections that don't apply are marked and explained. Proof was collected 24 Nov 2026.

| Baseline line | Status | Proof |
|---|---|---|
| 1. Secrets | N/A: the app has no secrets or API keys. | Pattern scan over the repo (api key / secret / token / password assignments, `ghp_`, `sk-`, `AKIA`) found nothing. `.gitignore` excludes `.env*`, usage data, caches. |
| 2. Dependencies | Pinned (`psutil==7.2.2`, `dissect.esedb==3.18`). | `pip-audit --skip-editable` -> "No known vulnerabilities found". CI runs it on every push. |
| 3. Authentication | N/A: no users. Writes need a per-run random token (32 bytes, `secrets.token_urlsafe`), compared in constant time. | `test_post_needs_token_origin_and_json`: no token / wrong token -> 403. |
| 4. Rate limits | No login or public endpoint. Per-app refresh (the only expensive action) allows one run at a time, at most every 20 s. | `App.refresh_apps`. |
| 5. Input | Settings are validated: numeric ranges, list sizes, string length, control characters rejected, unknown keys dropped, whole-number percents only. Body limited to 4 KB, JSON only. | `test_validate_rejects` (17 bad inputs), `test_validate_ignores_unknown_keys_and_lowercases_apps`, `test_oversize_and_bad_json`, `test_autostart_needs_bool`. All DOM output uses `textContent`; no `innerHTML`. |
| 6. Headers | CSP `default-src 'none'; script-src 'self'; style-src 'self'; ...; frame-ancestors 'none'` (no inline code, no `unsafe-*`), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, CORP/COOP `same-origin`, `no-store`, server banner hidden. | `test_security_headers_and_csp`, `test_no_inline_script_or_style_in_page`. |
| 7. Endpoints that do work | Every POST requires the token, same origin (`Origin` allowlist, `Sec-Fetch-Site`), and `Content-Type: application/json`. Host header allowlist blocks DNS rebinding. | `test_foreign_host_refused`, `test_post_needs_token_origin_and_json`. |
| 4/7. Local binding | Server binds `127.0.0.1` only (nothing on the network can reach it). | `serve()` in `server.py`; `test_listens_only_on_loopback`. |
| 8. Database | N/A: no database. Data is JSON files in `%APPDATA%\datawatch`. | - |
| 9. Privacy | Collects only byte counts per adapter / per app / per day. Nothing is sent anywhere. Per-app history is read from a temporary copy of the Windows database that is deleted right after parsing; only totals are kept. Delete-my-data = delete the folder. Export = the JSON files. No logs of typed text. | `srum.refresh` (`finally: copy.unlink`), README "Settings and data". |
| 10. Prove it | Attack tests run against the running server. | `tests/test_server.py` (10 tests) + `tests/test_core.py` (38 tests): 62 passed in total (server, core, icons and MCP tests). Built `datawatch.exe` smoke-tested: `/`, `/app.js`, `/style.css`, `/api/state` all 200. |

## AI assistant connector (MCP)

| Concern | Control | Proof |
|---|---|---|
| Who can connect | Nobody remote: it is a stdio program the person's own AI client launches on their own PC. No port, no token, no account. | `test_stdio_end_to_end` |
| What it can read | Totals only (usage, per-app MB, limits). No paths, user names or PC details. App names have control characters stripped and are length-capped (they are data, not instructions). | `test_usage_summary`, `test_app_usage_without_data_and_with_data` |
| What it can change | Nothing by default. `set_limits` exists only with `--allow-write`, validates like the UI, ignores unknown fields. | `test_set_limits_is_blocked_without_flag`, `test_set_limits_with_flag_validates` |
| Bad input | Malformed JSON-RPC, unknown tools and methods return protocol errors, never stack traces. | `test_bad_requests` |

## App icons

Icons are extracted from `.exe` paths Windows itself reported, using Windows' icon API, with the paths passed to
PowerShell through a JSON file. The web page only ever sees an id (SHA-1 of the app name) and requests
`/icon/<40 hex>.png`; anything else is a 404 and no file path reaches the page (`test_icon_route_serves_only_valid_ids`,
`test_read_icon_only_by_valid_id`). File paths are not saved in the per-app cache.

## Personal and PC details before publishing

`scripts/privacy_scan.py` reads this PC's details live (Windows user name, profile path, computer name, local IP and MAC
addresses, git name and e-mail) and fails if any of them, or any e-mail, IP address, `C:\Users\<name>` path, Windows SID,
MAC address, host name or secret format appears in a tracked file, a file name, any commit message or diff in the git
history, or the commit author identities. The public GitHub login is allowed (public by design). A pre-push hook runs it,
so a push is refused until it is clean, and CI runs it again. Private words (for example a real name) can be added one per
line in the git-ignored `.privacy-terms`.

- Result 24 Nov 2026: 8 private markers checked, 0 problems (files and full history).
- Built `datawatch.exe` checked: the user name appears nowhere in the exe, including inside its compressed Python modules
  (PyInstaller stores relative paths such as `datawatch\app.py`). Release exes are built by GitHub Actions, not uploaded by hand.

## Other things worth knowing

- **Admin rights:** only the optional per-app refresh needs them, and Windows shows its own prompt each time. The
  elevated command is fixed (`esentutl /y <system file> /vss /d <our file>`); the destination path is rejected if it
  contains shell metacharacters (`test_snapshot_rejects_unsafe_path`).
- **Notifications** pass text through environment variables, never through the PowerShell script text.
- **Start with Windows** writes one value under the current user's `Run` key and nothing else; untick it to remove it.
- **Unsigned exe:** releases are not code-signed, so SmartScreen may warn. The release lists a SHA-256 and the
  source is here to build yourself.
- **Reporting a problem:** open a GitHub issue; for something sensitive, use the repository's private security advisory.
