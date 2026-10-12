"""Representative HikerAPI payloads for tests (shape per the v2 docs)."""

from __future__ import annotations

SAMPLE_PROFILE_PAYLOAD = {
    "status": "ok",
    "user": {
        "pk": 787132,
        "id": "787132",
        "username": "natgeo",
        "full_name": "National Geographic",
        "is_private": False,
        "is_verified": True,
        "media_count": 31529,
        "follower_count": 274988955,
        "following_count": 193,
        "biography": "Step into wonder. Business enquiries: hello@natgeo.com",
        "external_url": "http://visitstore.bio/natgeo",
        "bio_links": [
            {"url": "http://visitstore.bio/natgeo", "title": "Store"},
            {"url": "https://natgeo.com/work-with-us", "title": "Work with us"},
        ],
        "public_email": "partners@natgeo.com",
        "contact_phone_number": "",
        "public_phone_number": "+1 555 0100",
        "business_category_name": "Media/News Company",
        "category_name": None,
        "is_business": True,
    },
}

# Same profile as a bare user object (no "user" wrapper), with stringy scalars.
STRINGY_PROFILE_PAYLOAD = {
    "pk": "999",
    "username": "creator",
    "full_name": "A Creator",
    "follower_count": "12345",
    "following_count": "210",
    "media_count": "42",
    "is_private": "false",
    "is_verified": 1,
    "biography": "fintech educator | hi@creator.example.org",
    "external_url": "",
    "bio_links": [],
    "public_email": "",
    "contact_phone_number": "+44 20 7946 0000",
    "public_phone_number": "",
    "category_name": "Education",
}
