from __future__ import annotations

import pytest

from app.ai.schemas import DossierDraft
from app.providers.ai import GeminiProvider
from app.providers.errors import (
    AIConfigError,
    AIModelError,
    AIRateLimitError,
    AIResponseError,
)


class FakeAIError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"ai error {code}")
        self.code = code


class FakeResponse:
    def __init__(self, parsed=None, text=None) -> None:
        self.parsed = parsed
        self.text = text


class FakeModels:
    def __init__(self, results) -> None:
        self._results = list(results)
        self.calls = 0
        self.last_kwargs: dict = {}

    def generate_content(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        item = self._results.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeClient:
    def __init__(self, results) -> None:
        self.models = FakeModels(results)


def build(results, **overrides) -> tuple[GeminiProvider, FakeClient]:
    client = FakeClient(results)
    params = dict(sleeper=lambda _delay: None, rand=lambda: 1.0)
    params.update(overrides)
    provider = GeminiProvider("test-key", "gemini-test", client=client, **params)
    return provider, client


def test_structured_success_uses_parsed() -> None:
    provider, client = build([FakeResponse(parsed=DossierDraft(summary="hello"))])
    result = provider.generate_structured(prompt="p", system="s", schema=DossierDraft)
    assert isinstance(result, DossierDraft)
    assert result.summary == "hello"
    assert client.models.last_kwargs["model"] == "gemini-test"


def test_text_json_fallback_is_parsed() -> None:
    provider, _ = build([FakeResponse(text='{"summary": "from text"}')])
    result = provider.generate_structured(prompt="p", system="s", schema=DossierDraft)
    assert result.summary == "from text"


def test_malformed_json_raises_response_error() -> None:
    provider, _ = build([FakeResponse(text="not json at all")])
    with pytest.raises(AIResponseError):
        provider.generate_structured(prompt="p", system="s", schema=DossierDraft)


def test_schema_validation_failure_raises_response_error() -> None:
    provider, _ = build(
        [FakeResponse(text='{"criterionScores": [{"name": "x", "score": 999}]}')]
    )
    with pytest.raises(AIResponseError):
        provider.generate_structured(prompt="p", system="s", schema=DossierDraft)


def test_empty_response_raises_response_error() -> None:
    provider, _ = build([FakeResponse(text=None)])
    with pytest.raises(AIResponseError):
        provider.generate_structured(prompt="p", system="s", schema=DossierDraft)


def test_rate_limit_retries_then_succeeds() -> None:
    provider, client = build(
        [FakeAIError(429), FakeResponse(parsed=DossierDraft(summary="ok"))], max_attempts=3
    )
    result = provider.generate_structured(prompt="p", system="s", schema=DossierDraft)
    assert result.summary == "ok"
    assert client.models.calls == 2


def test_rate_limit_exhausted_raises() -> None:
    provider, _ = build([FakeAIError(429), FakeAIError(429), FakeAIError(429)], max_attempts=3)
    with pytest.raises(AIRateLimitError):
        provider.generate_structured(prompt="p", system="s", schema=DossierDraft)


def test_model_error_is_not_retried() -> None:
    provider, client = build([FakeAIError(400)])
    with pytest.raises(AIModelError):
        provider.generate_structured(prompt="p", system="s", schema=DossierDraft)
    assert client.models.calls == 1


@pytest.mark.parametrize("key,model", [("", "m"), ("k", "")])
def test_missing_config_raises(key: str, model: str) -> None:
    with pytest.raises(AIConfigError):
        GeminiProvider(key, model, client=FakeClient([]))
