# ISP & LAN Diagnostic Center

A Windows desktop tool for read-only network diagnostics, built with Python 3.12,
PySide6, psutil, Windows networking commands, and SQLite. Measurements and
reports stay on this computer unless you explicitly accept Ookla's terms and
run an internet speed test. No telemetry or automatic network configuration
changes are performed.

## Features

- Overview of actual adapters, addresses, gateway, DNS servers, link speed, and proxy status.
- Background one-click audit with per-check statuses and cancellation.
- TCP reachability to `1.1.1.1` and `8.8.8.8`; gateway/public ICMP checks; bounded DNS queries; and Windows `tracert`.
- Official Ookla Speedtest CLI integration only. Missing CLI, unsupported JSON, or unaccepted terms are clearly reported; no substitute speed test is used.
- Optional TCP iperf3 test only when the user enters a private IPv4 address for an authorized LAN server. UDP is deliberately not run.
- Rule-based findings with evidence and cautious confidence, independent download/upload package compliance, SQLite history, and local HTML/JSON/CSV reports with optional redaction.
- Read-only PowerShell adapter, route, DHCP, DNS, interface metric, and firewall profile inspection.

## Windows setup (PowerShell)

Install Python 3.12 first if `py -3.12 --version` is unavailable. The project is
compatible with the requested Python 3.12 runtime.

```powershell
cd C:\Users\talha\Documents\net-shooter
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Or launch with `.\run.bat` after installing the dependencies. No global
PowerShell execution policy changes are required; if activation is restricted,
use `.\.venv\Scripts\python.exe main.py` instead.

## Ookla Speedtest CLI

Download and install the official application from
<https://www.speedtest.net/apps/cli>. Make sure `speedtest.exe` is on `PATH` or
in a standard installation directory. The application inspects the installed
version and `--help` output before running JSON-formatted tests. The user must
explicitly accept the license/data terms in Settings. Tests contact Ookla and
a selected speed test server; the application does not send its reports.

## Optional LAN throughput test

Install iperf3 on this computer and start an iperf3 server on a computer you
own or are authorized to test. Enter its private IPv4 address in Settings.
Without that address, the check is marked `NOT TESTED`. Only TCP client tests
against private IPv4 hosts are implemented. The app does not discover or probe
other devices.

## Configuration and local data

- ISP package and unverified reference values: Settings tab or `config/settings.json`.
- Default download package: 7 Mbps. Upload package is unset until configured.
- Reference observations (3.2 Mbps down / 1.2 Mbps up) are clearly marked as
  user-provided and are never presented as test results.
- SQLite history: `data/history.sqlite3`.
- Application log: `logs/application.log`.
- Reports: `reports/` by default; change the folder in Settings.
- Reports can redact IP addresses and identifying fields. Review a report before
  sharing it; redaction cannot guarantee removal of every identifying detail.

Download compliance values are troubleshooting indicators, not an ISP SLA.
ICMP filtering can affect ping and traceroute without interrupting internet
access. Adapter traffic is aggregate traffic and cannot identify the application
that generated it. A low result alone does not prove ISP throttling.

## Tests

```powershell
python -m pytest
```

Tests use simulated fixtures only for unit-test validation; the application
does not display those fixture values as measurements.

## Limitations

- No Python 3.12 interpreter or Ookla CLI is bundled. Install them separately.
- Windows PowerShell collection relies on standard Windows cmdlets; fields may
  be omitted on older, non-Windows, or localized systems.
- Hardware-specific duplex/driver details and Wi-Fi fields depend on Windows
  command output and driver support.
- DNS response times, ping, and traceroute can be affected by filtering,
  host load, or routing policy.
- UDP iperf testing, detailed historical charting, external test-server
  comparisons, and conclusive ISP provisioning/throttling verification are not
  implemented.
