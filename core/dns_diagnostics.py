"""Bounded DNS queries to the system resolver and configured DNS servers."""

from __future__ import annotations

import random
import socket
import struct
import time


def _query_packet(domain: str, query_id: int) -> bytes:
    labels = domain.rstrip(".").encode("idna").split(b".")
    question = b"".join(bytes((len(label),)) + label for label in labels) + b"\0"
    return struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0) + question + struct.pack("!HH", 1, 1)


def query_dns_server(server: str, domain: str, timeout: float = 2.0) -> dict:
    query_id = random.randrange(0, 65536)
    packet = _query_packet(domain, query_id)
    started = time.perf_counter()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, (server, 53))
            response, _ = sock.recvfrom(4096)
        elapsed = (time.perf_counter() - started) * 1000
        if len(response) < 12:
            raise ValueError("DNS response was too short.")
        response_id, flags, questions, answers, _, _ = struct.unpack("!HHHHHH", response[:12])
        if response_id != query_id:
            raise ValueError("DNS response ID did not match the query.")
        rcode = flags & 0xF
        if rcode:
            raise OSError(f"DNS server returned response code {rcode}.")
        return {
            "server": server, "domain": domain, "status": "PASSED" if answers else "WARNING",
            "response_ms": elapsed, "answer_count": answers, "question_count": questions,
        }
    except (OSError, ValueError, struct.error) as exc:
        return {"server": server, "domain": domain, "status": "FAILED", "reason": str(exc)}


def run_dns_diagnostics(configured_servers: list[str]) -> dict:
    domains = ("google.com", "microsoft.com", "cloudflare.com")
    system_results = []
    for domain in domains:
        started = time.perf_counter()
        try:
            socket.getaddrinfo(domain, None, type=socket.SOCK_STREAM)
            system_results.append({
                "domain": domain, "status": "PASSED",
                "response_ms": (time.perf_counter() - started) * 1000,
                "resolver": "Windows system resolver",
            })
        except socket.gaierror as exc:
            system_results.append({
                "domain": domain, "status": "FAILED", "reason": str(exc),
                "resolver": "Windows system resolver",
            })
    direct_results = []
    for server in configured_servers:
        for domain in domains:
            direct_results.append(query_dns_server(server, domain))
    return {
        "status": "PASSED" if any(item["status"] == "PASSED" for item in system_results) else "WARNING",
        "system_resolver": system_results,
        "configured_server_queries": direct_results,
        "configured_servers": configured_servers,
        "note": "Direct tests use bounded UDP DNS queries; system resolver calls use Windows configuration.",
    }
