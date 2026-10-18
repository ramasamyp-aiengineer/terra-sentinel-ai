"""Connectors: SSRF protection for user-supplied links, size/redirect limits, Open-Meteo parsing."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from app.core.config import settings
from app.services.data import connectors
from app.services.data.connectors import FetchError

PUBLIC = lambda host: ["93.184.216.34"]  # noqa: E731


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/a.csv",  # plain http is off by default
        "ftp://example.com/a.csv",
        "file:///etc/passwd",
        "https://user:pw@example.com/a.csv",
        "https://127.0.0.1/a.csv",
        "https://169.254.169.254/latest/meta-data",  # cloud metadata endpoint
        "https://10.0.0.5/internal.csv",
        "https://[::1]/a.csv",
        "https:///nohost",
    ],
)
def test_dangerous_urls_are_refused(url):
    with pytest.raises(FetchError):
        connectors.validate_url(url, PUBLIC)


def test_hostname_resolving_to_private_address_is_refused():
    with pytest.raises(FetchError, match="private or internal"):
        connectors.validate_url("https://innocent.example.com/a.csv", lambda h: ["10.1.2.3"])


def test_fetch_ok_returns_filename_and_bytes():
    def handler(req):
        return httpx.Response(200, content=b"point_id,lat,lon\nA,1,2\n", headers={"content-type": "text/csv"})

    name, data = connectors.fetch_url("https://data.example.org/files/points.csv", client_for(handler), PUBLIC)
    assert name == "points.csv" and data.startswith(b"point_id")


def test_redirect_to_internal_address_is_blocked():
    def handler(req):
        if req.headers["host"] == "data.example.org":
            return httpx.Response(302, headers={"location": "https://169.254.169.254/latest/meta-data"})
        return httpx.Response(200, content=b"secret")

    with pytest.raises(FetchError, match="private or internal"):
        connectors.fetch_url("https://data.example.org/x.csv", client_for(handler), PUBLIC)


def test_redirect_loop_is_capped():
    def handler(req):
        return httpx.Response(302, headers={"location": "https://data.example.org/again"})

    with pytest.raises(FetchError, match="redirect"):
        connectors.fetch_url("https://data.example.org/x.csv", client_for(handler), PUBLIC)


def test_oversized_download_is_stopped(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    def handler(req):
        return httpx.Response(200, content=b"x" * (2 * 1024 * 1024))  # no content-length header from the mock stream

    with pytest.raises(FetchError, match="larger than"):
        connectors.fetch_url("https://data.example.org/big.csv", client_for(handler), PUBLIC)


def test_html_page_is_rejected_with_helpful_message():
    def handler(req):
        return httpx.Response(200, content=b"<html>login</html>", headers={"content-type": "text/html; charset=utf-8"})

    with pytest.raises(FetchError, match="web page"):
        connectors.fetch_url("https://data.example.org/share", client_for(handler), PUBLIC)


def test_http_error_status_is_reported():
    with pytest.raises(FetchError, match="404"):
        connectors.fetch_url("https://data.example.org/x.csv", client_for(lambda r: httpx.Response(404)), PUBLIC)


def test_fetch_rain_parses_open_meteo_and_drops_today():
    seen = {}

    def handler(req):
        seen.update(dict(req.url.params))
        return httpx.Response(
            200,
            json={"daily": {"time": ["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"], "precipitation_sum": [0.0, 12.34, None, 55.0]}},
        )

    today = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
    df = connectors.fetch_rain(79.57, 30.55, "IN-UK-CHM", days=30, client=httpx.Client(transport=httpx.MockTransport(handler)), today=today)
    assert list(df["date"].dt.strftime("%Y-%m-%d")) == ["2026-10-13", "2026-10-14"]  # null day and today (partial) dropped
    assert df["precip_mm"].tolist() == [0.0, 12.3]
    assert seen["past_days"] == "30" and seen["latitude"] == "30.55" and seen["longitude"] == "79.57"


def test_fetch_rain_clamps_days_and_reports_failures():
    seen = {}

    def ok(req):
        seen.update(dict(req.url.params))
        return httpx.Response(200, json={"daily": {"time": ["2026-10-01"], "precipitation_sum": [1.0]}})

    connectors.fetch_rain(0, 0, "X", days=500, client=httpx.Client(transport=httpx.MockTransport(ok)), today=datetime(2026, 10, 16, tzinfo=timezone.utc))
    assert seen["past_days"] == "92"
    with pytest.raises(FetchError):
        connectors.fetch_rain(0, 0, "X", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))


def test_request_is_pinned_to_the_validated_address_with_original_host_and_sni():
    seen = {}

    def handler(req):
        seen["url_host"] = req.url.host
        seen["host_header"] = req.headers["host"]
        seen["sni"] = req.extensions.get("sni_hostname")
        return httpx.Response(200, content=b"a,b\n1,2\n", headers={"content-type": "text/csv"})

    connectors.fetch_url("https://data.example.org:8443/f.csv", client_for(handler), PUBLIC)
    assert seen == {"url_host": "93.184.216.34", "host_header": "data.example.org:8443", "sni": "data.example.org"}


def test_dns_rebinding_cannot_swap_in_an_internal_address():
    """The resolver is asked once per hop; the connection must use that answer, never a second lookup."""
    calls = []

    def flaky_resolver(host):
        calls.append(host)
        return ["93.184.216.34"] if len(calls) == 1 else ["10.0.0.5"]

    hit = []

    def handler(req):
        hit.append(req.url.host)
        return httpx.Response(200, content=b"a,b\n1,2\n", headers={"content-type": "text/csv"})

    connectors.fetch_url("https://rebind.example.org/f.csv", client_for(handler), flaky_resolver)
    assert hit == ["93.184.216.34"] and len(calls) == 1


def test_ipv4_is_preferred_when_a_name_has_both_families():
    url, addrs = connectors.resolve_public("https://dual.example.org/x", lambda h: ["2606:4700::1", "93.184.216.34"])
    assert addrs[0] == "93.184.216.34"


def test_public_addresses_are_still_allowed():
    for a in ("8.8.8.8", "93.184.216.34", "2606:4700:4700::1111"):
        connectors._check_public(a)