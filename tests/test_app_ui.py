"""Headless UI tests using Streamlit's AppTest. No Gemini API key or network needed."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.pdf_factory import encrypt_pdf, make_pdf

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(monkeypatch) -> AppTest:
    # A fake key lets the chat part render; no request is made unless a message is sent.
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-ui-tests")
    return AppTest.from_file(APP_PATH, default_timeout=30).run()


def _upload(at: AppTest, name: str, data: bytes) -> AppTest:
    at.file_uploader[0].set_value((name, data, "application/pdf"))
    return at.run()


def _click_process(at: AppTest) -> AppTest:
    at.button[0].click()
    return at.run()


def _metrics(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def test_app_renders_document_section_and_chat_without_errors(app):
    assert not app.exception
    assert [s.value for s in app.subheader] == ["📄 Document processing"]
    assert len(app.file_uploader) == 1
    assert len(app.chat_input) == 1  # existing chat interface is still there


def test_document_section_still_renders_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)

    at = AppTest.from_file(APP_PATH, default_timeout=30).run()

    assert not at.exception
    assert len(at.file_uploader) == 1
    assert any("GOOGLE_API_KEY" in e.value for e in at.error)  # original message kept
    assert len(at.chat_input) == 0


def test_uploader_only_accepts_pdf_and_a_single_file(app):
    uploader = app.file_uploader[0]

    assert uploader.allowed_type == [".pdf"]
    assert uploader.accept_multiple_files is False


def test_valid_pdf_shows_statistics_preview_and_chunks(app):
    pdf = make_pdf(["Hello from page one", "Greetings from page two"])

    _upload(app, "sample.pdf", pdf)
    assert any("sample.pdf" in m.value for m in app.markdown)
    assert any("Process PDF" in i.value for i in app.info)  # not processed until clicked

    _click_process(app)

    assert not app.exception
    metrics = _metrics(app)
    assert metrics["Pages"] == "2"
    assert metrics["Characters"] == str(len("Hello from page one") + len("Greetings from page two"))
    assert metrics["Chunks"] == "1"
    assert metrics["Pages without text"] == "0"
    assert app.button[0].label == "Reprocess PDF"
    areas = [t.value for t in app.text_area]
    assert any("--- Page 1 ---" in a and "Hello from page one" in a for a in areas)
    assert any("Greetings from page two" in a for a in areas)
    assert any("Inspect chunks (1)" in e.label for e in app.expander)


def test_changing_chunk_settings_and_reprocessing_updates_chunk_count(app):
    text = " ".join(f"word{i}" for i in range(300))  # ~2 000 characters
    _upload(app, "long.pdf", make_pdf([text]))
    _click_process(app)
    default_chunks = int(_metrics(app)["Chunks"])

    # Change the settings in their own run (a browser commits an input on blur,
    # which reruns the script) and click afterwards. Changing the inputs and
    # clicking within a single AppTest step did not trigger processing.
    app.number_input[0].set_value(300).run()  # chunk size
    app.number_input[1].set_value(50).run()  # overlap
    _click_process(app)

    assert int(_metrics(app)["Chunks"]) > default_chunks
    assert any("chunk size 300 and overlap 50" in s.value for s in app.success)


def test_overlap_not_smaller_than_chunk_size_disables_processing(app):
    _upload(app, "sample.pdf", make_pdf(["some text"]))

    app.number_input[0].set_value(100)
    app.number_input[1].set_value(200)
    app.run()

    assert any("Overlap must be smaller" in e.value for e in app.error)
    assert app.button[0].disabled


def test_scanned_style_pdf_explains_the_limitation(app):
    _upload(app, "scan.pdf", make_pdf(["", ""]))
    _click_process(app)

    assert not app.exception
    assert any("No extractable text" in w.value and "OCR" in w.value for w in app.warning)
    assert _metrics(app)["Pages"] == "2"
    assert _metrics(app)["Characters"] == "0"


def test_blank_page_among_text_pages_triggers_a_warning(app):
    _upload(app, "gap.pdf", make_pdf(["One", "", "Three"]))
    _click_process(app)

    assert not app.exception
    assert any("page 2" in w.value for w in app.warning)
    assert _metrics(app)["Pages without text"] == "1"


@pytest.mark.parametrize(
    "name, data, expected",
    [
        ("empty.pdf", b"", "empty"),
        ("fake.pdf", b"this is definitely not a pdf", "valid PDF"),
        ("broken.pdf", b"%PDF-1.4\n" + b"\x00garbage" * 50, "corrupted"),
    ],
)
def test_bad_files_show_a_friendly_error_not_a_crash(app, name, data, expected):
    _upload(app, name, data)
    _click_process(app)

    assert not app.exception
    assert any(expected in e.value for e in app.error)
    assert not app.metric  # no statistics for a failed file


def test_password_protected_pdf_shows_a_friendly_error(app):
    _upload(app, "locked.pdf", encrypt_pdf(make_pdf(["secret"]), "pw"))
    _click_process(app)

    assert not app.exception
    assert any("password-protected" in e.value for e in app.error)


def test_oversized_file_is_rejected_with_the_limit_in_the_message(app):
    oversized = make_pdf(["x"]) + b"0" * (20 * 1024 * 1024 + 1)

    _upload(app, "huge.pdf", oversized)

    assert not app.exception
    assert any("larger than the 20 MB limit" in e.value for e in app.error)
    assert len(app.button) == 0  # nothing to process


def test_uploading_a_different_file_clears_old_results(app):
    _upload(app, "first.pdf", make_pdf(["First document"]))
    _click_process(app)
    assert _metrics(app)

    _upload(app, "second.pdf", make_pdf(["Second document"]))

    assert not app.metric  # stale results are not shown for the new file
    assert any("second.pdf" in m.value for m in app.markdown)


def test_removing_the_file_clears_results(app):
    _upload(app, "first.pdf", make_pdf(["First document"]))
    _click_process(app)
    assert _metrics(app)

    app.file_uploader[0].set_value(None)
    app.run()

    assert not app.metric
    assert not app.exception
