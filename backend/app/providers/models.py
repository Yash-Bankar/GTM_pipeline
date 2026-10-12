"""Typed, normalized Instagram profile produced from a HikerAPI response."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .emails import extract_emails


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return 0


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class HikerProfile(BaseModel):
    """A normalized Instagram profile.

    This is the stable shape the rest of the system consumes; provider field
    names never leak past this model.
    """

    model_config = ConfigDict(extra="ignore")

    username: str
    instagram_id: str
    full_name: str = ""
    biography: str = ""
    follower_count: int = 0
    following_count: int = 0
    media_count: int = 0
    external_url: str = ""
    bio_links: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    phone: str = ""
    category: str = ""
    is_private: bool = False
    is_verified: bool = False
    is_business: bool = False


def parse_profile_payload(payload: dict[str, Any]) -> HikerProfile:
    """Normalize a HikerAPI ``/v2/user/by/username`` payload.

    Accepts either the v2 wrapper (``{"user": {...}, "status": "ok"}``) or a bare
    user object. Field names are read leniently with sensible fallbacks.
    """
    user = payload.get("user") if isinstance(payload.get("user"), dict) else payload

    biography = _as_str(user.get("biography"))
    bio_links: list[str] = []
    for link in user.get("bio_links") or []:
        if isinstance(link, dict) and link.get("url"):
            bio_links.append(_as_str(link["url"]))

    emails: set[str] = set(extract_emails(biography))
    direct_email = _as_str(user.get("public_email")) or _as_str(user.get("business_email"))
    if direct_email:
        emails.add(direct_email.lower())

    category = (
        _as_str(user.get("category_name"))
        or _as_str(user.get("business_category_name"))
        or _as_str(user.get("category"))
    )
    phone = _as_str(user.get("contact_phone_number")) or _as_str(
        user.get("public_phone_number")
    )

    return HikerProfile(
        username=_as_str(user.get("username")),
        instagram_id=_as_str(
            user.get("pk") or user.get("id") or user.get("strong_id__")
        ),
        full_name=_as_str(user.get("full_name")),
        biography=biography,
        follower_count=_as_int(user.get("follower_count")),
        following_count=_as_int(user.get("following_count")),
        media_count=_as_int(user.get("media_count")),
        external_url=_as_str(user.get("external_url")),
        bio_links=bio_links,
        emails=sorted(emails),
        phone=phone,
        category=category,
        is_private=_as_bool(user.get("is_private")),
        is_verified=_as_bool(user.get("is_verified")),
        is_business=_as_bool(user.get("is_business")),
    )


def to_lead_fields(profile: HikerProfile, *, scraped_at: str | None = None) -> dict[str, str]:
    """Map a normalized profile to the canonical `IG Leads` column names.

    Keys match the sheet headers so the result can be written by the storage layer
    (or passed to `Lead`/`EnrichedLead` models) without column-index assumptions.
    """
    all_urls = list(profile.bio_links)
    if profile.external_url and profile.external_url not in all_urls:
        all_urls.insert(0, profile.external_url)

    return {
        "username": profile.username,
        "fullName": profile.full_name,
        "instagramId": profile.instagram_id,
        "followerCount": str(profile.follower_count),
        "followsCount": str(profile.following_count),
        "businessCategoryName": profile.category,
        "bio": profile.biography,
        "businessEmail": ",".join(profile.emails),
        "businessPhoneNumber": profile.phone,
        "profileUrl": f"https://www.instagram.com/{profile.username}/" if profile.username else "",
        "externalUrl": profile.external_url,
        "allExternalUrls": ",".join(all_urls),
        "scrapedAt": scraped_at or utc_now_iso(),
    }
