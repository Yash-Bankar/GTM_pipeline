"""V2-06 hotfix: strict contact extraction (phone + email).

Guards against the V2-05 regression where CSS/decimal noise and tracking
codes were stored as phone numbers, and against image-filename / transactional
addresses being stored as emails.
"""

from __future__ import annotations

from app.providers.emails import extract_emails, extract_phones, is_plausible_phone

# Strings that were wrongly stored as phone numbers in the live database.
GARBAGE_PHONES = (
    "35771933781168458101792575716",
    "4 4 0 0 0 3.99 4.27",
    "10512572169863695511792575716",
    "118923337488134913561792575716",
    "0 2.17-.01 2.444-.046 3.292-.036.858-.173 1.442-.374 1.943-.2.53-.474.976-.92 1.423",
    "01 2.39.046 3.229",
    "11.83 11.83 6.172 6.17",
    "0000000000",
    "150.03663003663004",
    # CSS / layout noise seen in page source.
    "1000 1000",
    "1070 1070",
    "11.03 11.68",
    "11.35.643",
    "1100 1100",
)

REAL_PHONES = (
    "+1 (415) 555-0199",
    "415-555-0199",
    "415.555.0199",
    "+44 20 7946 0958",
    "020 7946 0958",
    "(415) 555-0199",
    "01 23 45 67 89",
    "+14155550199",
)


def test_phone_extraction_ignores_tracking_codes_and_decimals() -> None:
    """Tracking codes and decimal/CSS noise must never become phone numbers."""
    for value in GARBAGE_PHONES:
        assert extract_phones(value) == [], f"expected {value!r} to be ignored"
        assert extract_phones(f"contact us {value} thanks") == [], value
        assert is_plausible_phone(value) is False, value


def test_phone_extraction_keeps_valid_formats() -> None:
    """Real, publicly listed numbers must still be extracted."""
    for value in REAL_PHONES:
        assert extract_phones(value) == [value], value
        assert is_plausible_phone(value) is True, value


def test_phone_extraction_ignores_dates_and_bare_runs() -> None:
    assert extract_phones("posted 2026-10-19") == []
    assert extract_phones("released 19.10.2026") == []
    # A bare contiguous digit run is unverifiable (ID/hash), not a phone.
    assert extract_phones("id 1269563717") == []
    # E.164 with a country code is accepted.
    assert extract_phones("+1269563717") == ["+1269563717"]


def test_phone_extraction_ignores_long_digit_strings() -> None:
    """E.164 allows at most 15 digits."""
    assert extract_phones("35771933781168458101792575716") == []
    assert is_plausible_phone("+1234567890123456") is False  # 16 digits
    assert is_plausible_phone("+123456789012345") is True  # 15 digits


def test_email_extraction_ignores_image_filenames() -> None:
    """Retina variants and image filenames are assets, not addresses."""
    for value in (
        "logo@2x.png",
        "hero@3x.jpg",
        "banner@2x.webp",
        "icon@3x.svg",
        "photo@2x",
    ):
        assert extract_emails(value) == [], value


def test_email_extraction_ignores_transactional_addresses() -> None:
    for value in (
        "noreply@creator.com",
        "no-reply@creator.com",
        "no_reply@creator.com",
        "donotreply@creator.com",
        "mailer-daemon@creator.com",
        "postmaster@creator.com",
    ):
        assert extract_emails(value) == [], value


def test_email_extraction_keeps_real_addresses() -> None:
    assert extract_emails("write to hi@creator.com") == ["hi@creator.com"]
    assert extract_emails("Contact: Sales@Creator.com") == ["sales@creator.com"]
