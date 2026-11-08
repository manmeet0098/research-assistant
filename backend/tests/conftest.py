"""Shared fixtures.

Every test runs against a throwaway SQLite file, a fake Claude client, and a mocked
HTTP layer, so the suite never touches the network, real API keys, or library.db.
"""
from types import SimpleNamespace

import anthropic
import httpx
import pytest
import respx
from fastapi.testclient import TestClient

import db
import llm
import main
import search
from helpers import PAPER

REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def auth_error() -> anthropic.AuthenticationError:
    return anthropic.AuthenticationError(
        "invalid x-api-key", response=httpx.Response(401, request=REQ), body=None
    )


def api_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=REQ)


class FakeStream:
    def __init__(self, fake):
        self.fake = fake

    def __enter__(self):
        if self.fake.error:
            raise self.fake.error
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        chunks = self.fake.chunks if self.fake.chunks is not None else [self.fake.reply]
        for i, chunk in enumerate(chunks):
            if self.fake.error_after is not None and i == self.fake.error_after:
                raise api_error()
            yield chunk

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self.fake.stop_reason)


class FakeLLM:
    """Stands in for anthropic.Anthropic. Records every request in `calls`."""

    def __init__(self):
        self.reply = "FAKE REPLY"
        self.chunks = None
        self.stop_reason = "end_turn"
        self.error = None
        self.error_after = None
        self.calls = []
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        block = SimpleNamespace(type="text", text=self.reply)
        return SimpleNamespace(content=[block], stop_reason=self.stop_reason)

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "_client", fake)
    return fake


@pytest.fixture(autouse=True)
def mock_http():
    """Any HTTP request not explicitly mocked raises instead of hitting the network."""
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture(autouse=True)
def fast_search(monkeypatch):
    monkeypatch.setattr(search, "S2_MIN_INTERVAL", 0)
    monkeypatch.setattr(search, "S2_RETRY_DELAY", 0)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def lenient_client():
    """Like `client`, but an unhandled server error comes back as a 500 response
    instead of re-raising inside the test, so bugs show up as failed assertions."""
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def saved_paper(client):
    """A paper saved through the API (abstract only)."""
    return client.post("/api/library", json=PAPER).json()
