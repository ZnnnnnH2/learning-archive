import pytest
import requests

from src.model_api import ModelAPIClient, ModelAPIError


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_payload_url_and_auth_header(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return DummyResponse(
            payload={"choices": [{"message": {"content": "{\"ok\": true}"}}]}
        )

    monkeypatch.setattr(requests, "post", fake_post)
    client = ModelAPIClient("https://example.com/v1/", "secret", 12)

    content = client.complete_text(
        model="qwen-plus",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=7,
    )

    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["payload"]["model"] == "qwen-plus"
    assert captured["payload"]["max_tokens"] == 7
    assert captured["timeout"] == 12
    assert content == "{\"ok\": true}"


def test_http_error_has_clear_message(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: DummyResponse(status_code=401, text="bad key"),
    )
    client = ModelAPIClient("https://example.com/v1", "secret", 12)

    with pytest.raises(ModelAPIError, match="HTTP 401"):
        client.complete_text(model="m", messages=[])


def test_empty_choices_error(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: DummyResponse(payload={"choices": []}),
    )
    client = ModelAPIClient("https://example.com/v1", "secret", 12)

    with pytest.raises(ModelAPIError, match="missing non-empty choices"):
        client.complete_text(model="m", messages=[])


def test_non_json_response_error(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: DummyResponse(payload=ValueError("no json"), text="<html>"),
    )
    client = ModelAPIClient("https://example.com/v1", "secret", 12)

    with pytest.raises(ModelAPIError, match="non-JSON"):
        client.complete_text(model="m", messages=[])
