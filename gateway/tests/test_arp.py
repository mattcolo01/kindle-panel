import asyncio

from app.arp import HAEndpointResolver, ip_for_mac, replace_url_host


def test_ip_for_mac_ignores_arp_scan_headers_and_case():
    output = """Interface: eth0, type: EN10MB
Starting arp-scan 1.10
192.168.1.8\tAA:BB:CC:DD:EE:FF\tHome Assistant
192.168.1.9\t00:11:22:33:44:55\tOther host
"""
    assert ip_for_mac(output, "aa:bb:cc:dd:ee:ff") == "192.168.1.8"
    assert ip_for_mac(output, "00:00:00:00:00:00") is None


def test_replace_url_host_preserves_scheme_and_port():
    assert replace_url_host("https://old.lan:8123", "192.168.1.8") == "https://192.168.1.8:8123"


def test_resolver_runs_arp_scan_after_failure_and_updates_url(monkeypatch):
    seen = []

    class Process:
        returncode = 0

        async def communicate(self):
            return b"192.168.1.8 aa:bb:cc:dd:ee:ff Home Assistant\n", b""

    async def run(*command, **kwargs):
        seen.append((command, kwargs))
        return Process()

    monkeypatch.setattr("app.arp.asyncio.create_subprocess_exec", run)
    resolver = HAEndpointResolver("http://old.lan:8123", "aa:bb:cc:dd:ee:ff", "eth0")
    assert asyncio.run(resolver.recover()) == "http://192.168.1.8:8123"
    assert seen[0][0] == ("arp-scan", "--localnet", "--numeric", "--interface", "eth0")
