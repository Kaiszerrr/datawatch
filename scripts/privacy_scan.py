"""Privacy scan: refuses to let personal or PC details leave this machine.

Run before every push (a pre-push hook does it for you):   python scripts/privacy_scan.py
Checks every tracked file AND the whole git history for:
  * this PC's details, read live (never stored in the repo): Windows user name, profile path, computer name,
    local IP and MAC addresses, the git author name and email
  * extra private words you list one per line in .privacy-terms (git-ignored; e.g. your real name)
  * generic leaks: e-mail addresses, IPv4 addresses, C:/Users/<name> paths, Windows SIDs, MAC addresses,
    DESKTOP-/LAPTOP- host names, common secret and token formats
Also checks commit author/committer identities. Prints where and what kind, never the value itself.
  --exe PATH   additionally scan a built .exe (raw bytes, UTF-8 and UTF-16) for your user name / profile path
Exit code 1 = something found (push blocked).
"""
import getpass
import os
import platform
import re
import socket
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_EMAIL = re.compile(r"(@users\.noreply\.github\.com|^noreply@anthropic\.com|^git@github\.com)$", re.I)
SAFE_USERS = {"public", "default", "all users", "user", "username", "name", "you", "<user>", "%username%", "yourname", "me"}
GENERIC = [
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")),
    ("IPv4 address", re.compile(r"(?<![\d.])(?!127\.|0\.0\.0\.0|255\.|1\.1\.1\.1|8\.8\.)(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")),
    ("user profile path", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+([^\\/\s\"'<>|:*?]+)", re.I)),
    ("home path", re.compile(r"/(?:home|Users)/([a-z][a-z0-9._-]{2,})/", re.I)),
    ("Windows SID", re.compile(r"S-1-5-21-\d+-\d+-\d+-\d+")),
    ("MAC address", re.compile(r"(?<![0-9A-Fa-f:-])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:-])")),
    ("PC host name", re.compile(r"\b(?:DESKTOP|LAPTOP|PC)-[A-Z0-9]{6,8}\b")),
    ("secret / token", re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("assigned secret", re.compile(r"(?i)\b(api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]")),
]
SKIP_EXT = {".png", ".ico", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".exe", ".dll", ".pyc", ".zip"}


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


def public_names():
    """Names that are public by design: your GitHub login (read from the gh CLI) and anything in .privacy-allow."""
    names = set()
    try:
        r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            names.add(r.stdout.strip().lower())
    except (OSError, subprocess.SubprocessError):
        pass
    allow = ROOT / ".privacy-allow"
    if allow.exists():
        names |= {x.strip().lower() for x in allow.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")}
    return names


def private_markers():
    """Words that must never appear anywhere. Read from this PC at run time."""
    m = {}

    def add(label, value):
        v = (value or "").strip()
        if len(v) >= 3 and v.lower() not in SAFE_USERS:
            m[v] = label
    add("Windows user name", getpass.getuser())
    add("Windows user name", os.environ.get("USERNAME"))
    add("computer name", os.environ.get("COMPUTERNAME"))
    add("computer name", platform.node())
    add("computer name", socket.gethostname())
    add("profile path", os.environ.get("USERPROFILE"))
    add("profile path", str(Path.home()))
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                add("local IP address", ip)
    except OSError:
        pass
    mac = f"{uuid.getnode():012x}"
    add("MAC address", ":".join(mac[i:i + 2] for i in range(0, 12, 2)))
    add("MAC address", "-".join(mac[i:i + 2] for i in range(0, 12, 2)))
    public = public_names()
    for key in ("user.email", "user.name"):
        v = git("config", key).strip()
        if v and not ALLOWED_EMAIL.search(v) and v.lower() not in public:
            add("git " + key, v)
    extra = ROOT / ".privacy-terms"
    if extra.exists():
        for line in extra.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                add("your private term", line)
    return m


def scan_text(text, where, markers, findings):
    low = text.lower()
    for value, label in markers.items():
        if value.lower() in low:
            findings.append((where, label))
    for kind, rx in GENERIC:
        for mt in rx.finditer(text):
            if kind == "email address" and ALLOWED_EMAIL.search(mt.group(0)):
                continue
            if kind in ("user profile path", "home path") and mt.group(1).lower() in SAFE_USERS:
                continue
            if kind == "IPv4 address" and not all(0 <= int(p) <= 255 for p in mt.group(0).split(".")):
                continue
            findings.append((where, kind))
            break


def scan_tree(markers, findings):
    for rel in git("ls-files").splitlines():
        scan_text(rel, f"file name {rel}", markers, findings)
        p = ROOT / rel
        if p.suffix.lower() in SKIP_EXT or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            findings.append((rel, "binary file tracked (cannot be scanned)"))
            continue
        for n, line in enumerate(text.splitlines(), 1):
            scan_text(line, f"{rel}:{n}", markers, findings)


def scan_history(markers, findings):
    log = git("log", "--all", "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B%x1e")
    for rec in log.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) < 6:
            continue
        sha, an, ae, cn, ce, body = parts[0][:8], parts[1], parts[2], parts[3], parts[4], parts[5]
        for who, email in (("author", ae), ("committer", ce)):
            if email and not ALLOWED_EMAIL.search(email):
                findings.append((f"commit {sha} {who} email", "personal e-mail in git history"))
        scan_text(f"{an} {cn} {body}", f"commit {sha} message/identity", {k: v for k, v in markers.items() if k.lower() not in public_names()}, findings)
    patch = git("log", "--all", "-p", "--format=commit %h", "--no-color")
    cur = "?"
    for line in patch.splitlines():
        if line.startswith("commit "):
            cur = line[7:15]
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            scan_text(line[1:], f"history, commit {cur}", markers, findings)          # drop the +/- diff marker


def scan_exe(path, markers, findings):
    data = Path(path).read_bytes()
    for value, label in markers.items():
        for enc in ("utf-8", "utf-16-le"):
            if value.lower().encode(enc) in data.lower():
                findings.append((str(path), f"{label} inside the exe ({enc})"))
                break


def main():
    markers = private_markers()
    findings = []
    scan_tree(markers, findings)
    scan_history(markers, findings)
    if "--exe" in sys.argv:
        scan_exe(sys.argv[sys.argv.index("--exe") + 1], markers, findings)
    seen = set()
    for where, kind in findings:
        if (where, kind) not in seen:
            seen.add((where, kind))
            print(f"FOUND  {kind}  ->  {where}")
    print(f"privacy scan: {len(markers)} private markers checked, {len(seen)} problem(s)")
    return 1 if seen else 0


if __name__ == "__main__":
    sys.exit(main())
