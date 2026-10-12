from __future__ import annotations

import httpx
import pytest

from app.providers.errors import HikerAPINotFoundError
from app.providers.hikerapi import HikerAPIClient
from app.providers.models import parse_media_payload

BASE_URL = "https://api.hikerapi.com/v2"

CLIPS_PAYLOAD = {
    "response": {
        "items": [
            {
                "media": {
                    "pk": "3870025531093850440",
                    "id": "3870025531093850440_1029649300",
                    "code": "DWllQsJCPX_",
                    "media_type": 2,
                    "product_type": "clips",
                    "taken_at": 1775566804,
                    "like_count": 51261,
                    "comment_count": 236,
                    "play_count": 1496248,
                    "caption": {"text": "Intruder alert!"},
                }
            }
        ]
    },
    "next_page_id": None,
}

BARE_LIST_PAYLOAD = [
    {
        "pk": "111",
        "code": "ABC",
        "media_type": 1,
        "product_type": "",
        "taken_at_ts": 1700000000,
        "caption_text": "hi there",
        "like_count": 5,
        "comment_count": 1,
        "play_count": 0,
    }
]


def build_client(handler, **overrides) -> HikerAPIClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    params = dict(sleeper=lambda _delay: None, rand=lambda: 1.0)
    params.update(overrides)
    return HikerAPIClient("test-key", http_client=http, **params)


def test_parse_clips_payload() -> None:
    posts, next_page = parse_media_payload(CLIPS_PAYLOAD)
    assert next_page == ""
    assert len(posts) == 1
    post = posts[0]
    assert post.post_id == "3870025531093850440"
    assert post.short_code == "DWllQsJCPX_"
    assert post.media_type == "2"
    assert post.product_type == "clips"
    assert post.caption == "Intruder alert!"
    assert post.like_count == 51261
    assert post.comment_count == 236
    assert post.play_count == 1496248
    assert post.taken_at == "1775566804"
    assert post.url == "https://www.instagram.com/p/DWllQsJCPX_/"


def test_parse_bare_list_payload() -> None:
    posts, _ = parse_media_payload(BARE_LIST_PAYLOAD)
    assert len(posts) == 1
    assert posts[0].post_id == "111"
    assert posts[0].caption == "hi there"
    assert posts[0].taken_at == "1700000000"


@pytest.mark.parametrize("payload", [{"response": {"items": []}}, {}, "garbage", None])
def test_parse_empty_or_invalid(payload) -> None:
    posts, next_page = parse_media_payload(payload)
    assert posts == []
    assert next_page == ""


def test_fetch_recent_posts_success() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["user_id"] = request.url.params.get("user_id")
        seen["key"] = request.headers.get("x-access-key")
        return httpx.Response(200, json=CLIPS_PAYLOAD)

    posts = build_client(handler).fetch_recent_posts("787132", limit=5, max_pages=2)
    assert seen["path"] == "/v2/user/medias"
    assert seen["user_id"] == "787132"
    assert seen["key"] == "test-key"
    assert len(posts) == 1


def test_fetch_recent_posts_paginates_until_limit() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={"response": {"items": [{"media": {"pk": "1", "code": "c1"}},
                                             {"media": {"pk": "2", "code": "c2"}}]},
                      "next_page_id": "p2"},
            )
        return httpx.Response(
            200, json={"response": {"items": [{"media": {"pk": "3", "code": "c3"}}]}}
        )

    posts = build_client(handler).fetch_recent_posts("1", limit=3, max_pages=5)
    assert [p.post_id for p in posts] == ["1", "2", "3"]
    assert calls["n"] == 2


def test_fetch_recent_posts_stops_at_limit() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"response": {"items": [{"media": {"pk": "1"}}]}, "next_page_id": "next"},
        )

    posts = build_client(handler).fetch_recent_posts("1", limit=1, max_pages=5)
    assert len(posts) == 1
    assert calls["n"] == 1  # limit reached, no second page


def test_fetch_recent_posts_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"status": "fail"})

    with pytest.raises(HikerAPINotFoundError):
        build_client(handler).fetch_recent_posts("1", limit=3)


def test_fetch_recent_posts_requires_user_id() -> None:
    from app.leads.validation import InvalidLeadInput

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        return httpx.Response(200, json={})

    with pytest.raises(InvalidLeadInput):
        build_client(handler).fetch_recent_posts("", limit=3)
