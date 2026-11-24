"""Optional 'start with Windows' via the current user's Run key (no admin needed, easy to undo)."""
import sys

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "datawatch"


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --background'
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{exe}" -m datawatch --background'


def is_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
            winreg.QueryValueEx(k, _NAME)
            return True
    except (OSError, ImportError):
        return False


def set_enabled(on: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, _NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(k, _NAME)
            except FileNotFoundError:
                pass
