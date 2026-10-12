"""Website crawling + email extraction (ported and hardened).

Ports the useful behaviour of the legacy ``website_crawler`` /
``enrichment_crawler`` (link-hub support, page text/links, email extraction)
without any dependency on the old SQLite stores, Streamlit or pipeline.

Security: strict URL validation and SSRF protections (scheme allow-list, host
block-list, DNS resolution + private/loopback/link-local rejection), response
size limits, timeouts, bounded redirects and bounded retries.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.common.retry import call_with_retry

from .emails import extract_emails

logger = logging.getLogger(__name__)

# Social/aggregator hosts we never crawl.
SKIP_DOMAINS = (
    "instagram.com",
    "threads.net",
    "facebook.com",
    "fb.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "pinterest.com",
    "linkedin.com",
)

# Paths that are never useful for contact/lead enrichment.
SKIP_PATH_PARTS = (
    "/privacy",
    "/terms",
    "/login",
    "/signin",
    "/signup",
    "/cart",
    "/checkout",
    "/unsubscribe",
)

LINK_HUB_DOMAINS = (
    "linktr.ee",
    "stan.store",
    "beacons.ai",
    "bio.site",
    "hoo.be",
    "direct.me",
    "pensight.com",
    "msha.ke",
    "milkshake.app",
    "solo.to",
    "campsite.bio",
    "taplink.cc",
    "linkin.bio",
    "withkoji.com",
    "lnk.bio",
)

USEFUL_KEYWORDS = (
    "about",
    "contact",
    "work with me",
    "work-with-me",
    "services",
    "coaching",
    "consulting",
    "course",
    "newsletter",
    "media kit",
    "media-kit",
    "collab",
    "partnership",
    "sponsor",
    "press",
    "podcast",
    "shop",
    "book",
    "freebie",
)

_BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".home.arpa")
_BLOCKED_HOSTS = frozenset({"localhost", "localhost.localdomain", "metadata.google.internal"})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class UnsafeUrlError(ValueError):
    """Raised when a URL fails validation or SSRF checks."""


def normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    value, _fragment = urldefrag(value)
    return value.rstrip("/")


def _make_soup(html: str) -> BeautifulSoup:
    """Parse HTML, preferring lxml when available and falling back otherwise."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001 - any parser/feature error -> stdlib
        return BeautifulSoup(html, "html.parser")


def host_matches(host: str, domain: str) -> bool:
    host = (host or "").lower().removeprefix("www.")
    domain = (domain or "").lower().removeprefix("www.")
    return host == domain or host.endswith(f".{domain}")


def should_skip_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    return any(host_matches(host, domain) for domain in SKIP_DOMAINS) or any(
        part in path for part in SKIP_PATH_PARTS
    )


def is_link_hub(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return any(host_matches(host, domain) for domain in LINK_HUB_DOMAINS)


def is_blocked_host(host: str) -> bool:
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host in _BLOCKED_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES)


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def default_resolver(host: str) -> list[str]:
    """Resolve a host to its IP addresses (empty list on failure)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    return sorted({info[4][0] for info in infos})


def validate_url(url: str, resolver=default_resolver) -> str:
    """Validate a URL for safe outbound fetching; return the normalized URL.

    Raises :class:`UnsafeUrlError` for disallowed schemes, blocked hosts, or
    hosts that resolve to non-public addresses.
    """
    normalized = normalize_url(url)
    if not normalized:
        raise UnsafeUrlError("empty URL")
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"scheme '{parsed.scheme or 'none'}' is not allowed")
    host = parsed.hostname or ""
    if not host:
        raise UnsafeUrlError("URL has no host")
    if is_blocked_host(host):
        raise UnsafeUrlError(f"host '{host}' is not allowed")
    addresses = resolver(host)
    if not addresses:
        raise UnsafeUrlError(f"host '{host}' could not be resolved")
    if any(not _is_public_ip(address) for address in addresses):
        raise UnsafeUrlError(f"host '{host}' resolves to a non-public address")
    return normalized


@dataclass
class FetchedPage:
    """The outcome of fetching one page."""

    url: str
    resolved_url: str = ""
    domain: str = ""
    title: str = ""
    text: str = ""
    links: list[dict] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    http_status: int = 0
    status: str = "done"  # done | error | blocked
    error: str = ""


class _RetryableHttp(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"retryable HTTP {status}")
        self.status = status


def _clean_text(soup: BeautifulSoup, max_chars: int) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "img", "form"]):
        tag.decompose()
    for selector in ("nav", "footer", "header"):
        for tag in soup.select(selector):
            tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:max_chars]


def _extract_visible_links(soup: BeautifulSoup, base_url: str, max_links: int) -> list[dict]:
    links: list[dict] = []
    seen: set[str] = set()
    for tag in soup.select("a[href]"):
        href = (tag.get("href") or "").strip()
        if href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        label = re.sub(r"\s+", " ", tag.get_text(" ", strip=True))[:160]
        absolute = normalize_url(urljoin(base_url, href))
        if not absolute or absolute in seen:
            continue
        seen.add(absolute)
        links.append({"label": label, "url": absolute})
        if len(links) >= max_links:
            break
    return links


def _score_link(link: dict, start_url: str) -> int:
    url = link.get("url", "")
    label = link.get("label", "")
    if should_skip_url(url):
        return -100
    score = 0
    if urlparse(url).netloc == urlparse(start_url).netloc:
        score += 2
    if is_link_hub(start_url) and urlparse(url).netloc != urlparse(start_url).netloc:
        score += 5
    haystack = f"{label} {url}".lower()
    for keyword in USEFUL_KEYWORDS:
        if keyword in haystack:
            score += 10
    return score


class WebsiteCrawler:
    """Crawl a bounded set of pages from one or more start URLs."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        max_pages: int = 5,
        max_links_per_page: int = 30,
        max_bytes: int = 2_000_000,
        max_attempts: int = 2,
        max_redirects: int = 3,
        text_max_chars: int = 6000,
        user_agent: str = "SynpoGTM/0.1",
        client: httpx.Client | None = None,
        resolver=default_resolver,
    ) -> None:
        self._timeout = timeout
        self._max_pages = max(1, int(max_pages))
        self._max_links_per_page = max_links_per_page
        self._max_bytes = max_bytes
        self._max_attempts = max(1, int(max_attempts))
        self._max_redirects = max(0, int(max_redirects))
        self._text_max_chars = text_max_chars
        self._user_agent = user_agent
        self._resolver = resolver
        self._owns_http = client is None
        self._http = client or httpx.Client(
            timeout=timeout, follow_redirects=False, headers={"User-Agent": user_agent}
        )

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "WebsiteCrawler":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- public API ---------------------------------------------------------

    def crawl(self, start_urls: list[str]) -> tuple[list[FetchedPage], list[str]]:
        """Crawl up to ``max_pages`` pages. Returns ``(pages, emails)``.

        Invalid/blocked start URLs produce a ``blocked`` page (not an exception),
        so a single bad link never fails the whole job.
        """
        pages: list[FetchedPage] = []
        emails: set[str] = set()
        seen: set[str] = set()

        candidates: list[str] = []
        for raw in start_urls:
            normalized = normalize_url(raw)
            if normalized and normalized not in candidates:
                candidates.append(normalized)

        while candidates and len(pages) < self._max_pages:
            current = candidates.pop(0)
            if current in seen:
                continue
            seen.add(current)

            try:
                safe_url = validate_url(current, self._resolver)
            except UnsafeUrlError as exc:
                pages.append(
                    FetchedPage(url=current, status="blocked", error=str(exc))
                )
                continue

            page = self._fetch(safe_url)
            pages.append(page)
            emails.update(page.emails)

            if page.status == "done":
                ranked = sorted(
                    page.links, key=lambda link: _score_link(link, safe_url), reverse=True
                )
                for link in ranked:
                    if len(candidates) + len(pages) >= self._max_pages:
                        break
                    target = normalize_url(link["url"])
                    if (
                        target
                        and target not in seen
                        and target not in candidates
                        and _score_link(link, safe_url) > 0
                    ):
                        candidates.append(target)

        return pages, sorted(emails)

    # -- internals ----------------------------------------------------------

    def _request_once(self, url: str) -> tuple[int, str, bytes, str]:
        with self._http.stream("GET", url) as response:
            status = response.status_code
            if status in _RETRYABLE_STATUSES:
                raise _RetryableHttp(status)
            content_type = response.headers.get("content-type", "")
            if status in _REDIRECT_STATUSES:
                return status, content_type, b"", response.headers.get("location", "")

            body = bytearray()
            if status == 200 and "html" in content_type:
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) >= self._max_bytes:
                        break
            return status, content_type, bytes(body), ""

    def _fetch(self, url: str) -> FetchedPage:
        current = url
        redirects = 0

        def _retryable(exc: BaseException) -> bool:
            return isinstance(exc, (_RetryableHttp, httpx.TransportError))

        while True:
            try:
                status, content_type, body, location = call_with_retry(
                    lambda: self._request_once(current),
                    max_attempts=self._max_attempts,
                    retryable=_retryable,
                )
            except _RetryableHttp as exc:
                return self._error_page(url, current, status=exc.status, error=f"HTTP {exc.status}")
            except httpx.TransportError as exc:
                return self._error_page(url, current, error=f"{type(exc).__name__}: {exc}")

            if status in _REDIRECT_STATUSES and location and redirects < self._max_redirects:
                try:
                    current = validate_url(urljoin(current, location), self._resolver)
                except UnsafeUrlError as exc:
                    return self._error_page(url, current, status_label="blocked", error=str(exc))
                redirects += 1
                continue
            if status in _REDIRECT_STATUSES:
                return self._error_page(url, current, status=status, error="too many redirects")
            if status >= 400:
                return self._error_page(url, current, status=status, error=f"HTTP {status}")
            if "html" not in content_type:
                return self._error_page(
                    url, current, status=status, error=f"non-HTML content: {content_type or 'unknown'}"
                )

            html = body.decode("utf-8", "replace")
            soup = _make_soup(html)
            title = (
                re.sub(r"\s+", " ", soup.title.get_text(" ", strip=True)) if soup.title else ""
            )
            text = _clean_text(soup, self._text_max_chars)
            links = _extract_visible_links(soup, current, self._max_links_per_page)
            return FetchedPage(
                url=url,
                resolved_url=current,
                domain=urlparse(current).netloc.lower(),
                title=title,
                text=text,
                links=links,
                emails=extract_emails(html + " " + text),
                http_status=status,
                status="done",
            )

    @staticmethod
    def _error_page(
        url: str, resolved: str, *, status: int = 0, status_label: str = "error", error: str
    ) -> FetchedPage:
        return FetchedPage(
            url=url,
            resolved_url=resolved,
            domain=urlparse(resolved).netloc.lower(),
            http_status=status,
            status=status_label,
            error=error,
        )
