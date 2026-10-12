from __future__ import annotations

import pytest

from app.leads.validation import InvalidLeadInput, parse_lead_input


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@Some.Creator", "some.creator"),
        ("  Some.Creator  ", "some.creator"),
        ("Some.Creator", "some.creator"),
        ("https://www.instagram.com/Some.Creator/", "some.creator"),
        ("instagram.com/Some.Creator", "some.creator"),
        ("http://instagram.com/abc/?hl=en", "abc"),
        ("https://www.instagram.com/abc#frag", "abc"),
        ("https://instagram.com/abc/extra/path", "abc"),
    ],
)
def test_parse_valid(raw: str, expected: str) -> None:
    parsed = parse_lead_input(raw)
    assert parsed.username.lower() == expected  # original case is preserved
    assert parsed.normalized == expected
    assert parsed.profile_url == f"https://www.instagram.com/{expected}/"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "https://example.com/foo",
        "https://instagram.com.evil.com/foo",
        "https://www.instagram.com/p/ABC123",
        "https://www.instagram.com/reel/xyz/",
        "https://www.instagram.com/",
        "bad handle!",
        "a" * 31,
        ".leading",
        "trailing.",
        "dou..ble",
    ],
)
def test_parse_invalid(raw: str) -> None:
    with pytest.raises(InvalidLeadInput):
        parse_lead_input(raw)
