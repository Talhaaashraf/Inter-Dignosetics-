"""Read-only local adapter, route, proxy, and firewall inspection."""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from typing import Any

import psutil

from core.process import run_command


def _powershell(script: str, timeout: float = 12) -> Any:
    executable = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not executable:
        return {"available": False, "reason": "PowerShell was not found."}
    result = run_command(
        [executable, "-NoProfile", "-NonInteractive", "-Command", script], timeout
    )
    if result.returncode:
        return {"available": False, "reason": result.stderr.strip() or "PowerShell query failed."}
    text = result.stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"available": False, "reason": "Windows returned unrecognized diagnostic output."}


def collect_network_info() -> dict:
    interfaces = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    counters = psutil.net_io_counters(pernic=True)
    adapters = []
    for name, addresses in interfaces.items():
        addr_data = []
        for item in addresses:
            addr_data.append({
                "family": str(item.family),
                "address": item.address,
                "netmask": item.netmask,
                "broadcast": item.broadcast,
            })
        stat = stats.get(name)
        is_up = bool(stat and stat.isup)
        if not is_up and not any(a["family"] in {"AddressFamily.AF_INET", "AddressFamily.AF_INET6"} for a in addr_data):
            continue
        metric = counters.get(name)
        adapters.append({
            "name": name,
            "addresses": addr_data,
            "is_up": is_up,
            "mtu": stat.mtu if stat else None,
            "speed_mbps": stat.speed if stat and stat.speed > 0 else None,
            "bytes_sent": metric.bytes_sent if metric else None,
            "bytes_received": metric.bytes_recv if metric else None,
            "errors_in": metric.errin if metric else None,
            "errors_out": metric.errout if metric else None,
            "drops_in": metric.dropin if metric else None,
            "drops_out": metric.dropout if metric else None,
        })

    windows = {}
    if platform.system() == "Windows":
        script = (
            "$ErrorActionPreference='Stop'; $a=Get-NetAdapter -ErrorAction SilentlyContinue | "
            "Select-Object Name,InterfaceDescription,Status,LinkSpeed,MacAddress,DriverInformation;"
            "$c=Get-NetIPConfiguration -ErrorAction SilentlyContinue | Select-Object InterfaceAlias,"
            "IPv4Address,IPv6Address,IPv4DefaultGateway,DNSServer;"
            "$d=Get-NetIPInterface -ErrorAction SilentlyContinue | Select-Object InterfaceAlias,"
            "AddressFamily,Dhcp,InterfaceMetric,NlMtu;"
            "$r=Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
            "Sort-Object RouteMetric | "
            "Select-Object InterfaceAlias,NextHop,RouteMetric;"
            "$f=Get-NetFirewallProfile -ErrorAction SilentlyContinue | "
            "Select-Object Name,Enabled;"
            "$o=[ordered]@{adapters=@($a);configuration=@($c);interfaces=@($d);routes=@($r);"
            "firewall=@($f);winhttp=(netsh winhttp show proxy | Out-String);"
            "userProxy=[ordered]@{http=$env:HTTP_PROXY;https=$env:HTTPS_PROXY}};"
            "$o | ConvertTo-Json -Depth 6 -Compress"
        )
        try:
            windows = _powershell(script)
        except (OSError, subprocess.SubprocessError) as exc:
            windows = {"available": False, "reason": str(exc)}
    routes = windows.get("routes", []) if isinstance(windows, dict) else []
    if isinstance(routes, dict):
        routes = [routes]
    gateway = routes[0].get("NextHop") if routes else None
    dns_servers = []
    config = windows.get("configuration", []) if isinstance(windows, dict) else []
    if isinstance(config, dict):
        config = [config]
    for item in config:
        dns = item.get("DNSServer", {}).get("ServerAddresses", []) if isinstance(item.get("DNSServer"), dict) else []
        dns_servers.extend(dns or [])
    addresses = []
    for adapter in adapters:
        addresses.extend((adapter["name"], address) for address in adapter["addresses"])
    return {
        "hostname": platform.node(),
        "operating_system": platform.platform(),
        "adapters": adapters,
        "windows": windows,
        "gateway": gateway,
        "dns_servers": sorted(set(dns_servers)),
        "local_addresses": addresses,
        "vpn_indicators": [
            item["name"] for item in adapters
            if re.search(r"vpn|wireguard|tunnel|openvpn|tailscale|zerotier", item["name"], re.I)
        ],
        "proxy_detected": bool(
            (windows.get("userProxy", {}) if isinstance(windows, dict) else {}).get("http")
            or (windows.get("userProxy", {}) if isinstance(windows, dict) else {}).get("https")
        ),
    }


def internet_connection() -> dict:
    """Check TCP reachability to well-known HTTPS endpoints (not only ICMP)."""
    import socket
    results = []
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.create_connection((host, 443), timeout=3):
                results.append({"host": host, "status": "PASSED", "latency_ms": None})
        except OSError as exc:
            results.append({"host": host, "status": "WARNING", "reason": str(exc)})
    connected = any(r["status"] == "PASSED" for r in results)
    return {
        "status": "PASSED" if connected else "WARNING",
        "results": results,
        "connected": connected,
        "note": "TCP reachability failure does not distinguish filtering from a wider network outage.",
    }
