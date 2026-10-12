from __future__ import annotations

import httpx
import pytest

from app.providers.website import (
    UnsafeUrlError,
    WebsiteCrawler,
    normalize_url,
    validate_url,
)


def resolver(host: str) -> list[str]:
    if host.endswith("internal.test"):
        return ["10.0.0.5"]
    if host in ("localhost", "127.0.0.1"):
        return [host]
    return ["93.184.216.34"]  # a public address


def build(handler, **overrides) -> WebsiteCrawler:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    overrides.setdefault("max_attempts", 1)
    return WebsiteCrawler(client=client, resolver=resolver, **overrides)


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://example.org/x", "gopher://example.org", ""],
)
def test_validate_rejects_disallowed_scheme(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url(url, resolver)


@pytest.mark.parametrize("url", ["http://localhost/x", "http://internal.test/x", "http://127.0.0.1/"])
def test_validate_rejects_internal_hosts(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url(url, resolver)


def test_validate_accepts_public_https() -> None:
    assert validate_url("https://example.org/contact/", resolver) == "https://example.org/contact"


def test_normalize_url_adds_scheme_and_strips_fragment() -> None:
    assert normalize_url("example.org/x#frag") == "https://example.org/x"


def test_crawl_missing_website_returns_empty() -> None:
    crawler = build(lambda request: httpx.Response(200, text=""))
    pages, emails = crawler.crawl([])
    assert pages == []
    assert emails == []


def test_crawl_success_extracts_title_text_links_and_emails() -> None:
    html = """
    <html><head><title>Acme Finance</title></head>
    <body>
      <nav>menu</nav>
      <h1>Work with us</h1>
      <p>Email hello@acme.example.org</p>
      <a href="/contact">Contact</a>
      <a href="mailto:press@acme.example.org">Press</a>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    pages, emails = build(handler, max_pages=1).crawl(["https://example.org/"])
    assert len(pages) == 1
    page = pages[0]
    assert page.status == "done"
    assert page.title == "Acme Finance"
    assert "Work with us" in page.text
    assert any(link["url"] == "https://example.org/contact" for link in page.links)
    assert "hello@acme.example.org" in emails
    assert "press@acme.example.org" in emails


def test_crawl_blocks_private_start_url() -> None:
    crawler = build(lambda request: httpx.Response(200, text="secret"))
    pages, _ = crawler.crawl(["http://internal.test/admin"])
    assert len(pages) == 1
    assert pages[0].status == "blocked"
    assert "non-public" in pages[0].error or "not allowed" in pages[0].error


def test_crawl_blocks_redirect_to_private_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "http://internal.test/secret"})
        return httpx.Response(200, text="secret")  # pragma: no cover

    pages, _ = build(handler).crawl(["https://example.org/"])
    assert pages[0].status == "blocked"


def test_crawl_enforces_response_size_limit() -> None:
    big = "<html><body>" + ("A" * 5000) + "</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=big)

    pages, _ = build(handler, max_bytes=50, text_max_chars=20).crawl(["https://example.org/"])
    assert pages[0].status == "done"
    assert len(pages[0].text) <= 20


def test_crawl_non_html_is_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, text="{}")

    pages, _ = build(handler).crawl(["https://example.org/"])
    assert pages[0].status == "error"
    assert "non-HTML" in pages[0].error


def test_crawl_transport_error_is_error_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    pages, _ = build(handler).crawl(["https://example.org/"])
    assert pages[0].status == "error"


def test_crawl_follows_useful_same_host_links_only() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/":
            body = (
                '<a href="/contact">Contact</a>'
                '<a href="/about">About</a>'
                '<a href="https://instagram.com/someone">IG</a>'
                '<a href="/privacy">Privacy</a>'
            )
            return httpx.Response(200, headers={"content-type": "text/html"}, text=body)
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>ok</html>")

    pages, _ = build(handler).crawl(["https://example.org/"])
    assert set(requested) == {"/", "/contact", "/about"}
    assert len(pages) == 3
