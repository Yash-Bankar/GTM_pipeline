"""Evidence assembly for AI prompts.

Evidence is plain data pulled from the Sheets repositories. It is treated as
**untrusted** by the prompt layer (see ``prompts.py``) and is never executed or
followed as instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PageEvidence:
    url: str
    title: str
    text: str


@dataclass
class Evidence:
    lead_id: str
    username: str = ""
    full_name: str = ""
    bio: str = ""
    category: str = ""
    follower_count: int = 0
    business_email: str = ""
    business_phone: str = ""
    external_urls: list[str] = field(default_factory=list)
    posts: list[str] = field(default_factory=list)
    pages: list[PageEvidence] = field(default_factory=list)

    def has_content(self) -> bool:
        """True when there is more than a bare username to reason about."""
        return bool(self.bio.strip() or self.posts or self.pages)

    def source_urls(self) -> list[str]:
        urls: list[str] = []
        for url in [*self.external_urls, *(page.url for page in self.pages)]:
            if url and url not in urls:
                urls.append(url)
        return urls


def _split_urls(raw: str) -> list[str]:
    return [part.strip() for part in str(raw or "").replace("\n", ",").split(",") if part.strip()]


def build_evidence(
    *,
    lead_values: dict[str, str],
    post_rows: list[dict[str, str]],
    page_rows: list[dict[str, str]],
    max_posts: int = 10,
    max_pages: int = 5,
    text_chars: int = 1500,
) -> Evidence:
    urls: list[str] = []
    for raw in (lead_values.get("all_external_urls", ""), lead_values.get("external_url", "")):
        for url in _split_urls(raw):
            if url not in urls:
                urls.append(url)

    posts = [
        str(row.get("caption", "")).strip()[:text_chars]
        for row in post_rows[:max_posts]
        if str(row.get("caption", "")).strip()
    ]
    pages = [
        PageEvidence(
            url=str(row.get("url", "")),
            title=str(row.get("title", ""))[:300],
            text=str(row.get("text", ""))[:text_chars],
        )
        for row in page_rows[:max_pages]
        if str(row.get("text", "")).strip() or str(row.get("title", "")).strip()
    ]

    try:
        followers = int(str(lead_values.get("follower_count", "") or 0))
    except ValueError:
        followers = 0

    return Evidence(
        lead_id=str(lead_values.get("lead_id", "")),
        username=str(lead_values.get("username", "")),
        full_name=str(lead_values.get("full_name", "")),
        bio=str(lead_values.get("bio", ""))[:text_chars],
        category=str(lead_values.get("business_category_name", "")),
        follower_count=followers,
        business_email=str(lead_values.get("business_email", "")),
        business_phone=str(lead_values.get("business_phone_number", "")),
        external_urls=urls,
        posts=posts,
        pages=pages,
    )
