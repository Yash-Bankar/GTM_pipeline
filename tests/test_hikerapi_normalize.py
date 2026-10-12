from __future__ import annotations

from app.providers.emails import extract_emails
from app.providers.models import parse_profile_payload, to_lead_fields
from hiker_fixtures import SAMPLE_PROFILE_PAYLOAD, STRINGY_PROFILE_PAYLOAD


def test_parse_wrapped_payload() -> None:
    profile = parse_profile_payload(SAMPLE_PROFILE_PAYLOAD)

    assert profile.username == "natgeo"
    assert profile.instagram_id == "787132"
    assert profile.full_name == "National Geographic"
    assert profile.follower_count == 274988955
    assert profile.following_count == 193
    assert profile.media_count == 31529
    assert profile.category == "Media/News Company"
    assert profile.phone == "+1 555 0100"
    assert profile.external_url == "http://visitstore.bio/natgeo"
    assert profile.bio_links == [
        "http://visitstore.bio/natgeo",
        "https://natgeo.com/work-with-us",
    ]
    assert profile.is_verified is True
    assert profile.is_business is True
    assert profile.is_private is False


def test_emails_merge_direct_and_bio() -> None:
    profile = parse_profile_payload(SAMPLE_PROFILE_PAYLOAD)
    assert profile.emails == ["hello@natgeo.com", "partners@natgeo.com"]


def test_parse_bare_payload_coerces_scalars() -> None:
    profile = parse_profile_payload(STRINGY_PROFILE_PAYLOAD)

    assert profile.username == "creator"
    assert profile.instagram_id == "999"
    assert profile.follower_count == 12345
    assert profile.following_count == 210
    assert profile.media_count == 42
    assert profile.is_private is False
    assert profile.is_verified is True
    assert profile.category == "Education"
    assert profile.phone == "+44 20 7946 0000"
    assert profile.emails == ["hi@creator.example.org"]


def test_to_lead_fields_maps_canonical_headers() -> None:
    profile = parse_profile_payload(SAMPLE_PROFILE_PAYLOAD)
    fields = to_lead_fields(profile, scraped_at="2026-01-01T00:00:00+00:00")

    assert fields["username"] == "natgeo"
    assert fields["fullName"] == "National Geographic"
    assert fields["instagramId"] == "787132"
    assert fields["followerCount"] == "274988955"
    assert fields["followsCount"] == "193"
    assert fields["businessCategoryName"] == "Media/News Company"
    assert fields["businessEmail"] == "hello@natgeo.com,partners@natgeo.com"
    assert fields["businessPhoneNumber"] == "+1 555 0100"
    assert fields["profileUrl"] == "https://www.instagram.com/natgeo/"
    assert fields["externalUrl"] == "http://visitstore.bio/natgeo"
    assert fields["allExternalUrls"] == (
        "http://visitstore.bio/natgeo,https://natgeo.com/work-with-us"
    )
    assert fields["scrapedAt"] == "2026-01-01T00:00:00+00:00"


def test_extract_emails_filters_noise() -> None:
    text = "Reach me at hey@studio.com or logo@2x.png; also sentry.io is bad"
    assert extract_emails(text) == ["hey@studio.com"]
    assert extract_emails("") == []


def test_to_lead_fields_without_username_has_empty_profile_url() -> None:
    profile = parse_profile_payload({"username": ""})
    fields = to_lead_fields(profile)
    assert fields["profileUrl"] == ""
