"""Discover a LAN host by MAC address with arp-scan.

This is deliberately opt-in: ARP is a layer-2 protocol, so it cannot cross a
router and the gateway container must run on the host network with NET_RAW.
"""

import asyncio
import logging
import re
from urllib.parse import urlsplit, urlunsplit

log = logging.getLogger(__name__)

ARP_LINE_RE = re.compile(
    r"^\s*(?P<ip>(?:\d{1,3}\.){3}\d{1,3})\s+(?P<mac>(?:[0-9a-f]{2}:){5}[0-9a-f]{2})(?:\s|$)",
    re.IGNORECASE,
)


def replace_url_host(url: str, ip: str) -> str:
    """Keep scheme and port of *url*, replacing only its host with an IPv4."""
    parts = urlsplit(url)
    if not parts.hostname:
        raise ValueError("URL has no host")
    port = f":{parts.port}" if parts.port is not None else ""
    return urlunsplit((parts.scheme, f"{ip}{port}", parts.path, parts.query, parts.fragment))


def ip_for_mac(output: str, mac: str) -> str | None:
    wanted = mac.lower()
    for line in output.splitlines():
        match = ARP_LINE_RE.match(line)
        if match and match["mac"].lower() == wanted:
            return match["ip"]
    return None


class HAEndpointResolver:
    """Keep the most recently found HA URL and rescan only after failure."""

    def __init__(self, url: str, mac: str | None, interface: str | None):
        self.url = url
        self._mac = mac
        self._interface = interface
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._mac is not None

    async def recover(self) -> str | None:
        """Return a newly discovered URL, or None when recovery failed."""
        if not self.enabled:
            return None
        async with self._lock:
            command = ["arp-scan", "--localnet", "--numeric"]
            if self._interface:
                command.extend(("--interface", self._interface))
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
            except (OSError, TimeoutError) as e:
                log.warning("Could not run arp-scan to recover Home Assistant: %s", type(e).__name__)
                return None
            if process.returncode != 0:
                log.warning("arp-scan failed while recovering Home Assistant: %s", stderr.decode(errors="replace").strip())
                return None
            ip = ip_for_mac(stdout.decode(errors="replace"), self._mac or "")
            if not ip:
                log.warning("arp-scan did not find Home Assistant MAC %s", self._mac)
                return None
            self.url = replace_url_host(self.url, ip)
            log.info("Home Assistant rediscovered at %s", self.url)
            return self.url
