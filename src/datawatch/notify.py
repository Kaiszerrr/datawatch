"""Windows desktop notification (balloon tip) via PowerShell. Text goes through environment variables, never
into the script, so it can't inject code."""
import os
import subprocess

_SCRIPT = (
    "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
    "$n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Warning; "
    "$n.Visible = $true; $n.ShowBalloonTip(15000, $env:DW_TITLE, $env:DW_TEXT, 'Warning'); "
    "Start-Sleep -Seconds 16; $n.Dispose()"
)


def send(title: str, text: str) -> None:
    env = dict(os.environ, DW_TITLE=title[:60], DW_TEXT=text[:250])
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", _SCRIPT],
                         env=env, creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
