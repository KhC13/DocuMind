"""Regression tests for the existing Gemini chat, using a fake client (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeChat:
    def __init__(self, calls, model, history, fail):
        self._calls, self._fail = calls, fail
        calls.append({"model": model, "history_len": len(history)})

    def send_message(self, prompt):
        if self._fail:
            raise RuntimeError("quota exceeded")
        self._calls[-1]["prompt"] = prompt
        return FakeResponse(f"echo: {prompt}")


class FakeClient:
    calls: list = []
    fail = False

    def __init__(self, api_key=None):
        self.api_key = api_key
        self.chats = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def create(self, model, history):
        return FakeChat(FakeClient.calls, model, history, FakeClient.fail)


@pytest.fixture
def chat_app(monkeypatch):
    FakeClient.calls, FakeClient.fail = [], False
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-ui-tests")
    monkeypatch.setattr("google.genai.Client", FakeClient)
    return AppTest.from_file(APP_PATH, default_timeout=30).run()


def test_chat_message_gets_a_reply_and_is_kept_in_history(chat_app):
    chat_app.chat_input[0].set_value("Hello").run()

    assert not chat_app.exception
    assert [m["role"] for m in chat_app.session_state["messages"]] == ["user", "assistant"]
    assert chat_app.session_state["messages"][1]["content"] == "echo: Hello"
    assert FakeClient.calls[0]["model"] == "gemini-3.6-flash"  # model id unchanged


def test_second_message_sends_the_earlier_conversation_as_history(chat_app):
    chat_app.chat_input[0].set_value("one").run()
    chat_app.chat_input[0].set_value("two").run()

    assert FakeClient.calls[0]["history_len"] == 0
    assert FakeClient.calls[1]["history_len"] == 2


def test_api_error_is_shown_and_not_stored_in_history(chat_app):
    FakeClient.fail = True

    chat_app.chat_input[0].set_value("Hello").run()

    assert any("Gemini API error" in e.value for e in chat_app.error)
    assert chat_app.session_state["messages"] == []


def test_processing_a_pdf_does_not_disturb_the_chat_history(chat_app):
    from tests.pdf_factory import make_pdf

    chat_app.chat_input[0].set_value("Hello").run()
    chat_app.file_uploader[0].set_value(("a.pdf", make_pdf(["text"]), "application/pdf")).run()
    chat_app.button[0].click().run()

    assert not chat_app.exception
    assert len(chat_app.session_state["messages"]) == 2
    assert len(FakeClient.calls) == 1  # PDF processing made no Gemini call
