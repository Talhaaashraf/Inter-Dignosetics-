"""Deterministic, evidence-bound root cause guidance."""

from __future__ import annotations


def analyze_findings(audit: dict, settings: dict) -> list[dict]:
    findings = []
    network = audit.get("network", {})
    package = audit.get("download_compliance", {})
    gateway = audit.get("gateway_ping", {})
    if package.get("status") in {"POOR", "CRITICAL"}:
        measured = package.get("actual_mbps")
        cap = package.get("package_mbps")
        findings.append({
            "title": "Measured download is below the configured package",
            "severity": "HIGH" if package.get("status") == "CRITICAL" else "MEDIUM",
            "evidence": f"Measured {measured:.2f} Mbps against a configured {cap:.2f} Mbps package ({package['compliance_percent']:.1f}%).",
            "potential_cause": "Possible provisioning, congestion, router, cabling, adapter, or competing traffic issue.",
            "confidence": "Medium" if audit.get("speedtest", {}).get("status") == "PASSED" else "Low",
            "recommendation": "Repeat at a different time and compare a second device on Ethernet; ask the ISP to verify the provisioned profile if the pattern persists.",
            "verification": "Run two or more official Ookla tests at different times.",
        })
    packet_loss = gateway.get("packet_loss_percent")
    if gateway.get("status") in {"WARNING", "FAILED"} and isinstance(packet_loss, (int, float)) and packet_loss > 0:
        findings.append({
            "title": "Gateway ICMP loss or non-response observed", "severity": "MEDIUM",
            "evidence": f"{gateway.get('failed', 'Unknown')} of {gateway.get('sent', 'unknown')} gateway pings did not reply.",
            "potential_cause": "Local link/router instability, or ICMP filtering/rate limiting.",
            "confidence": "Low",
            "recommendation": "Check the Ethernet connection and compare with another device; do not infer general internet failure from ping alone.",
            "verification": "Repeat the gateway ping and inspect adapter error counters.",
        })
    errors = [
        (adapter["name"], adapter.get("errors_in", 0) + adapter.get("errors_out", 0))
        for adapter in network.get("adapters", [])
        if isinstance(adapter.get("errors_in"), int) and isinstance(adapter.get("errors_out"), int)
    ]
    if any(total > 0 for _, total in errors):
        findings.append({
            "title": "Network adapter reports errors", "severity": "LOW",
            "evidence": "; ".join(f"{name}: {count} errors" for name, count in errors if count > 0),
            "potential_cause": "Driver, adapter, or physical-link issue.",
            "confidence": "Low",
            "recommendation": "Check Windows driver status and cabling; counters may be cumulative since adapter startup.",
            "verification": "Inspect Windows adapter statistics after a fresh sample.",
        })
    dns = audit.get("dns", {})
    if dns and not any(item.get("status") == "PASSED" for item in dns.get("system_resolver", [])):
        findings.append({
            "title": "System DNS resolution failed for all test domains", "severity": "HIGH",
            "evidence": "No successful response was recorded by the Windows system resolver.",
            "potential_cause": "DNS service, resolver configuration, or connectivity issue.",
            "confidence": "Medium",
            "recommendation": "Inspect configured DNS server reachability; this application does not change DNS configuration.",
            "verification": "Retry after confirming general connectivity.",
        })
    if not findings:
        findings.append({
            "title": "No clear local issue detected", "severity": "INFO",
            "evidence": "No implemented rule received measurements that crossed its diagnostic threshold.",
            "potential_cause": "Not determined.",
            "confidence": "Low",
            "recommendation": "Compare results across time and devices if symptoms continue.",
            "verification": "Run another complete audit when the issue is present.",
        })
    return findings
