"""External data connectors.

  fetch_url    download a CSV / GeoJSON from a link the user supplies
  fetch_rain   daily rainfall for a region centre from Open-Meteo (no API key)

``fetch_url`` is a server-side request made on behalf of a user-supplied address, so it
is a classic SSRF vector. It therefore: allows https only (http opt-in), resolves the
host and refuses private / loopback / link-local / reserved addresses, validates every
redirect hop, enforces a size cap while streaming, and has a hard timeout.
"""
from __future__ import annotations

import ipaddress
import socket
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import unquote, urljoin, urlparse

import httpx
import pandas as pd

from app.core.config import settings

MAX_REDIRECTS = 3
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
USER_AGENT = "TerraSentinel/0.1 (+decision-support; contact: ops)"


class FetchError(ValueError):
    """A user-facing problem fetching external data."""


Resolver = Callable[[str], list[str]]


def _default_resolver(host: str) -> list[str]:
    try:
        return sorted({ai[4][0] for ai in socket.getaddrinfo(host, None)})
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host {host!r}.") from exc


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_REFUSED = "That address points to a private or internal network and is not allowed."


def _embedded_ipv4(ip: ipaddress._BaseAddress) -> list[ipaddress.IPv4Address]:
    """IPv4 addresses hidden inside an IPv6 one (mapped, 6to4, Teredo, NAT64), which must pass the same test."""
    if not isinstance(ip, ipaddress.IPv6Address):
        return []
    found: list[ipaddress.IPv4Address] = []
    if ip.ipv4_mapped:
        found.append(ip.ipv4_mapped)
    if ip.sixtofour:
        found.append(ip.sixtofour)
    if ip.teredo:
        found.extend(ip.teredo)
    if ip in _NAT64:
        found.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return found


def _check_public(addr: str) -> None:
    """Allow only globally routable unicast addresses.

    ``is_global`` also rejects ranges the older blocklist missed: carrier-grade NAT (100.64.0.0/10, which
    holds some clouds' metadata service), benchmarking, documentation and reserved space.
    """
    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
    except ValueError as exc:
        raise FetchError(_REFUSED) from exc
    for candidate in (ip, *_embedded_ipv4(ip)):
        if not candidate.is_global or candidate.is_multicast or candidate.is_unspecified:
            raise FetchError(_REFUSED)

def resolve_public(url: str, resolver: Resolver | None = None) -> tuple[str, list[str]]:
    """Validate a link and return (url, the public addresses its host resolves to)."""
    p = urlparse(url.strip())
    allowed = {"https"} | ({"http"} if settings.allow_http_fetch else set())
    if p.scheme not in allowed:
        raise FetchError("Only https:// links are allowed." if not settings.allow_http_fetch else "Only http(s) links are allowed.")
    if not p.hostname:
        raise FetchError("The link has no host name.")
    if p.username or p.password:
        raise FetchError("Links with embedded credentials are not allowed.")
    host = p.hostname
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:  # not an IP literal -> a name that must be resolved
        literal = None
    if literal is not None:  # a literal IP skips DNS but must pass the same check
        addrs = [str(literal)]
    else:
        addrs = (resolver or _default_resolver)(host)
        if not addrs:
            raise FetchError(f"Could not resolve host {host!r}.")
    for addr in addrs:
        _check_public(addr)
    # IPv4 first: many hosts have no working IPv6 route, and the pinned address must be one we can reach.
    ordered = sorted(addrs, key=lambda a: ":" in a)
    return url.strip(), ordered


def validate_url(url: str, resolver: Resolver | None = None) -> str:
    return resolve_public(url, resolver)[0]


def pin_request(url: str, addrs: list[str]) -> tuple[str, dict[str, str], dict[str, str]]:
    """Rewrite ``url`` to connect to an address we already validated.

    Resolving the name once to check it and again to connect lets a hostile DNS server answer with a public
    address first and an internal one second (DNS rebinding). Connecting to the checked address, while still
    sending the original Host header and TLS server name, closes that window and keeps certificate checks.
    """
    u = httpx.URL(url)
    host = u.host
    netloc = host if u.port is None else f"{host}:{u.port}"
    return str(u.copy_with(host=addrs[0])), {"Host": netloc}, {"sni_hostname": host}


def _filename_from(url: str, headers: httpx.Headers) -> str:
    cd = headers.get("content-disposition", "")
    if "filename=" in cd:
        return unquote(cd.split("filename=")[-1].strip().strip('"; '))[:120]
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    if name and "." in name:
        return name[:120]
    ctype = headers.get("content-type", "")
    ext = "geojson" if "geo+json" in ctype else "json" if "json" in ctype else "csv"
    return f"download.{ext}"


def fetch_url(url: str, client: httpx.Client | None = None, resolver: Resolver | None = None) -> tuple[str, bytes]:
    """Download a file. Returns (filename, bytes). Raises FetchError with a clear reason."""
    limit = settings.max_upload_mb * 1024 * 1024
    own = client is None
    client = client or httpx.Client(timeout=settings.fetch_timeout_s, follow_redirects=False, headers={"User-Agent": USER_AGENT})
    try:
        current, addrs = resolve_public(url, resolver)
        for _ in range(MAX_REDIRECTS + 1):
            try:
                # Connect to the address we validated, not to whatever DNS says a moment later.
                target, host_header, ext = pin_request(current, addrs)
                with client.stream("GET", target, headers=host_header, extensions=ext) as resp:
                    if resp.is_redirect:
                        loc = resp.headers.get("location")
                        if not loc:
                            raise FetchError("The server sent a redirect without a destination.")
                        current, addrs = resolve_public(urljoin(current, loc), resolver)  # re-validate every hop
                        continue
                    if resp.status_code >= 400:
                        raise FetchError(f"The server answered {resp.status_code} for that link.")
                    declared = resp.headers.get("content-length")
                    if declared and int(declared) > limit:
                        raise FetchError(f"The file is larger than the {settings.max_upload_mb} MB limit.")
                    buf = bytearray()
                    for chunk in resp.iter_bytes():
                        buf.extend(chunk)
                        if len(buf) > limit:
                            raise FetchError(f"The file is larger than the {settings.max_upload_mb} MB limit.")
                    if not buf:
                        raise FetchError("The link returned an empty file.")
                    ctype = resp.headers.get("content-type", "")
                    if ctype.startswith("text/html"):
                        raise FetchError("The link returned a web page, not a data file. Use a direct download link.")
                    return _filename_from(current, resp.headers), bytes(buf)
            except httpx.TimeoutException as exc:
                raise FetchError("The server took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"Network error: {exc.__class__.__name__}.") from exc
        raise FetchError("Too many redirects.")
    finally:
        if own:
            client.close()


def fetch_rain(
    lon: float,
    lat: float,
    region_id: str,
    days: int = 60,
    client: httpx.Client | None = None,
    today: datetime | None = None,
) -> pd.DataFrame:
    """Recent daily precipitation (mm) for a point from Open-Meteo. Columns: region_id, date, precip_mm."""
    days = max(7, min(int(days), 92))  # the forecast endpoint serves up to 92 past days
    own = client is None
    client = client or httpx.Client(timeout=settings.fetch_timeout_s, headers={"User-Agent": USER_AGENT})
    try:
        resp = client.get(
            OPEN_METEO_FORECAST,
            params={"latitude": lat, "longitude": lon, "daily": "precipitation_sum", "past_days": days, "forecast_days": 1, "timezone": "UTC"},
        )
        if resp.status_code != 200:
            raise FetchError(f"Open-Meteo answered {resp.status_code}.")
        body = resp.json()
        daily = body.get("daily") or {}
        times, vals = daily.get("time"), daily.get("precipitation_sum")
        if not times or vals is None:
            raise FetchError("Open-Meteo returned no daily rainfall for that location.")
    except httpx.TimeoutException as exc:
        raise FetchError("Open-Meteo took too long to respond.") from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not reach Open-Meteo ({exc.__class__.__name__}).") from exc
    finally:
        if own:
            client.close()

    df = pd.DataFrame({"region_id": region_id, "date": pd.to_datetime(times), "precip_mm": vals})
    cutoff = pd.Timestamp((today or datetime.now(timezone.utc)).date())
    df = df[df["date"] < cutoff].dropna(subset=["precip_mm"])  # today's value is partial/forecast, not an observation
    df["precip_mm"] = df["precip_mm"].astype(float).round(1)
    if df.empty:
        raise FetchError("No observed rainfall was returned for that period.")
    return df.reset_index(drop=True)
