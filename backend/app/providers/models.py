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
    """Map a normalized profile to `leads` column names (snake_case).

    Keys match the database columns so the result can be written directly by the
    repository.
    """
    all_urls = list(profile.bio_links)
    if profile.external_url and profile.external_url not in all_urls:
        all_urls.insert(0, profile.external_url)

    return {
        "username": profile.username,
        "full_name": profile.full_name,
        "instagram_id": profile.instagram_id,
        "follower_count": str(profile.follower_count),
        "follows_count": str(profile.following_count),
        "business_category_name": profile.category,
        "bio": profile.biography,
        "business_email": ",".join(profile.emails),
        "business_phone_number": profile.phone,
        "profile_url": f"https://www.instagram.com/{profile.username}/" if profile.username else "",
        "external_url": profile.external_url,
        "all_external_urls": ",".join(all_urls),
        "scraped_at": scraped_at or utc_now_iso(),
    }


class HikerPost(BaseModel):
    """A normalized recent media item (post or reel)."""

    model_config = ConfigDict(extra="ignore")

    post_id: str
    short_code: str = ""
    media_type: str = ""
    product_type: str = ""
    caption: str = ""
    like_count: int = 0
    comment_count: int = 0
    play_count: int = 0
    taken_at: str = ""
    url: str = ""


def _caption_text(media: dict[str, Any]) -> str:
    caption = media.get("caption")
    if isinstance(caption, dict):
        text = caption.get("text")
        if text:
            return str(text)
    for key in ("caption_text", "accessibility_caption"):
        if media.get(key):
            return str(media[key])
    return ""


def _first_int(media: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if media.get(key) is not None:
            return _as_int(media[key])
    return 0


def parse_post_item(item: dict[str, Any]) -> HikerPost | None:
    """Normalize a single HikerAPI media item (lenient across v1/v2 shapes)."""
    media = item.get("media") if isinstance(item.get("media"), dict) else item
    if not isinstance(media, dict):
        return None

    post_id = _as_str(media.get("pk") or media.get("id") or media.get("strong_id__"))
    if not post_id:
        return None

    short_code = _as_str(media.get("code") or media.get("shortcode"))
    media_type = _as_str(media.get("media_type"))
    product_type = _as_str(media.get("product_type"))

    taken_at = _as_str(media.get("taken_at"))
    if not taken_at and media.get("taken_at_ts") is not None:
        taken_at = _as_str(media.get("taken_at_ts"))

    url = ""
    if short_code:
        url = f"https://www.instagram.com/p/{short_code}/"
    elif media.get("url"):
        url = _as_str(media.get("url"))

    return HikerPost(
        post_id=post_id,
        short_code=short_code,
        media_type=media_type,
        product_type=product_type,
        caption=_caption_text(media),
        like_count=_first_int(media, "like_count", "like_count_total"),
        comment_count=_first_int(media, "comment_count"),
        play_count=_first_int(media, "play_count", "view_count", "video_view_count"),
        taken_at=taken_at,
        url=url,
    )


def parse_media_payload(payload: Any) -> tuple[list[HikerPost], str]:
    """Parse a media response into ``(posts, next_page_id)``.

    Handles the documented v2 shape ``{"response": {"items": [...]}}`` as well as
    a bare list or ``{"items": [...]}``. ``next_page_id`` is read when present.
    """
    next_page_id = ""
    items: Any = payload

    if isinstance(payload, dict):
        next_page_id = _as_str(payload.get("next_page_id") or payload.get("end_cursor"))
        response = payload.get("response")
        if isinstance(response, dict):
            next_page_id = next_page_id or _as_str(response.get("next_page_id"))
            items = response.get("items") or response.get("media") or []
        elif isinstance(response, list):
            items = response
        else:
            items = payload.get("items") or []

    if not isinstance(items, list):
        items = []

    posts: list[HikerPost] = []
    for item in items:
        if isinstance(item, dict):
            post = parse_post_item(item)
            if post is not None:
                posts.append(post)
    return posts, next_page_id
