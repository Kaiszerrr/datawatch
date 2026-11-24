"""Reads cumulative byte counters of the PC's real network adapters (psutil)."""
import re

import psutil

# Virtual / tunnel adapters would count the same traffic twice (once inside, once outside the tunnel).
_VIRTUAL = re.compile(r"loopback|vethernet|virtual|vmware|vbox|hyper-v|tap-|tun|wintun|wireguard|vpn|proton|"
                      r"nordlynx|openvpn|bluetooth|npcap|pseudo|isatap|teredo|6to4|docker|wsl", re.I)


def is_physical(name: str, extra_exclude=()) -> bool:
    return not _VIRTUAL.search(name) and name not in set(extra_exclude)


def read_counters(extra_exclude=()) -> dict:
    out = {}
    for name, c in psutil.net_io_counters(pernic=True).items():
        if is_physical(name, extra_exclude):
            out[name] = (int(c.bytes_recv), int(c.bytes_sent))
    return out
