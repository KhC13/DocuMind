"""Tests for PDF extraction and text chunking (no Gemini API key needed)."""

from __future__ import annotations

import re

import pytest
from pypdf import PageObject
from pypdf import errors as pypdf_errors
from pypdf import PdfReader

from document_processor import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    Chunk,
    CorruptedPDFError,
    DocumentProcessingError,
    EmptyFileError,
    EncryptedPDFError,
    FileTooLargeError,
    InvalidFileError,
    PageText,
    chunk_pages,
    extract_pdf,
    split_text_spans,
    validate_file_size,
)
from tests.pdf_factory import encrypt_pdf, make_pdf


# --------------------------------------------------------------------------- #
# Extraction: valid PDFs
# --------------------------------------------------------------------------- #


def test_extracts_text_page_by_page_with_page_numbers():
    pdf = make_pdf(["Alpha on page one", "Beta on page two", "Gamma on page three"])

    document = extract_pdf(pdf, "three.pdf")

    assert document.filename == "three.pdf"
    assert document.page_count == 3
    assert [p.page_number for p in document.pages] == [1, 2, 3]
    assert document.pages[0].text == "Alpha on page one"
    assert document.pages[1].text == "Beta on page two"
    assert document.pages[2].text == "Gamma on page three"
    assert document.has_text
    assert document.empty_pages == []
    assert document.failed_pages == []


def test_char_count_is_sum_of_page_text_lengths():
    document = extract_pdf(make_pdf(["12345", "123"]))

    assert document.char_count == 8


def test_multiline_text_and_special_characters_survive():
    document = extract_pdf(make_pdf(["line one\nline two (in brackets) a\\b"]))

    text = document.pages[0].text
    assert "line one" in text and "line two" in text
    assert "(in brackets)" in text
    assert "a\\b" in text


def test_blank_page_in_the_middle_keeps_page_numbers():
    document = extract_pdf(make_pdf(["First", "", "Third"]))

    assert document.page_count == 3
    assert document.pages[1].text == ""
    assert document.empty_pages == [2]
    assert document.pages[2].page_number == 3
    assert document.has_text


# --------------------------------------------------------------------------- #
# Extraction: empty / scanned / unreadable / invalid input
# --------------------------------------------------------------------------- #


def test_pdf_without_text_is_not_an_error_but_reports_no_text():
    """Mimics a scanned PDF: valid pages, no text layer."""
    document = extract_pdf(make_pdf(["", ""]))

    assert document.page_count == 2
    assert document.char_count == 0
    assert not document.has_text
    assert document.empty_pages == [1, 2]
    assert chunk_pages(document.pages) == []


def test_zero_byte_file_raises_empty_file_error():
    with pytest.raises(EmptyFileError):
        extract_pdf(b"", "empty.pdf")


def test_non_pdf_content_raises_invalid_file_error():
    with pytest.raises(InvalidFileError):
        extract_pdf(b"just some plain text, not a PDF", "fake.pdf")


def test_wrong_extension_raises_invalid_file_error():
    with pytest.raises(InvalidFileError):
        extract_pdf(make_pdf(["hello"]), "notes.txt")


def test_extension_check_is_case_insensitive():
    assert extract_pdf(make_pdf(["hello"]), "REPORT.PDF").page_count == 1


def test_garbage_after_pdf_header_raises_corrupted_error():
    with pytest.raises(CorruptedPDFError):
        extract_pdf(b"%PDF-1.4\n" + b"\x00garbage" * 50, "broken.pdf")


def test_truncated_pdf_raises_corrupted_error():
    pdf = make_pdf(["some content"] * 3)

    with pytest.raises(CorruptedPDFError):
        extract_pdf(pdf[: len(pdf) // 2], "cut.pdf")


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-256"])
def test_password_protected_pdf_raises_encrypted_error(algorithm):
    protected = encrypt_pdf(make_pdf(["secret"]), "pw", algorithm=algorithm)

    with pytest.raises(EncryptedPDFError):
        extract_pdf(protected, "locked.pdf")


def test_pdf_encrypted_with_empty_user_password_is_still_readable():
    """Owner-password-only protection opens with an empty user password."""
    protected = encrypt_pdf(make_pdf(["readable"]), "", owner_password="owner")

    document = extract_pdf(protected, "owner_only.pdf")

    assert document.pages[0].text == "readable"


def test_missing_decryption_dependency_is_reported_as_encrypted(monkeypatch):
    protected = encrypt_pdf(make_pdf(["secret"]), "pw")

    def fail(self, password):
        raise pypdf_errors.DependencyError("cryptography is required")

    monkeypatch.setattr(PdfReader, "decrypt", fail)

    with pytest.raises(EncryptedPDFError):
        extract_pdf(protected, "aes.pdf")


def test_file_over_size_limit_raises_with_helpful_message():
    pdf = make_pdf(["hello"])

    with pytest.raises(FileTooLargeError) as excinfo:
        extract_pdf(pdf, "big.pdf", max_size_bytes=10)

    assert "MB" in str(excinfo.value)


def test_validate_file_size_boundary():
    validate_file_size(100, 100)  # exactly at the limit is allowed
    with pytest.raises(FileTooLargeError):
        validate_file_size(101, 100)


def test_all_expected_errors_share_a_base_class():
    for error in (
        EmptyFileError,
        InvalidFileError,
        FileTooLargeError,
        EncryptedPDFError,
        CorruptedPDFError,
    ):
        assert issubclass(error, DocumentProcessingError)


def test_failure_on_one_page_is_recorded_and_other_pages_survive(monkeypatch):
    original = PageObject.extract_text
    calls = {"n": 0}

    def flaky(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", flaky)

    document = extract_pdf(make_pdf(["one", "two", "three"]))

    assert document.failed_pages == [2]
    assert document.pages[1].text == ""
    assert document.pages[0].text == "one"
    assert document.pages[2].text == "three"


def test_failure_on_every_page_raises_corrupted_error(monkeypatch):
    def always_fail(self, *args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(PageObject, "extract_text", always_fail)

    with pytest.raises(CorruptedPDFError):
        extract_pdf(make_pdf(["one", "two"]))


# --------------------------------------------------------------------------- #
# Chunking: empty and short input
# --------------------------------------------------------------------------- #


def test_defaults_are_the_documented_values():
    assert DEFAULT_CHUNK_SIZE == 1000
    assert DEFAULT_CHUNK_OVERLAP == 150


def test_no_pages_gives_no_chunks():
    assert chunk_pages([]) == []


@pytest.mark.parametrize("text", ["", "   ", "\n\n \t"])
def test_empty_or_whitespace_text_gives_no_chunks(text):
    assert chunk_pages([PageText(1, text)]) == []


def test_short_document_gives_a_single_chunk():
    chunks = chunk_pages([PageText(1, "Hello world.")])

    assert chunks == [
        Chunk(text="Hello world.", page_number=1, chunk_index=0, page_numbers=(1,))
    ]


def test_chunk_to_dict_has_documented_keys():
    chunk = chunk_pages([PageText(4, "Hello world.")])[0]

    assert chunk.to_dict() == {
        "text": "Hello world.",
        "page_number": 4,
        "chunk_index": 0,
        "page_numbers": [4],
    }


def test_text_exactly_chunk_size_is_one_chunk():
    chunks = chunk_pages([PageText(1, "x" * 100)], chunk_size=100, overlap=10)

    assert len(chunks) == 1
    assert len(chunks[0].text) == 100


def test_tiny_chunk_size_works():
    chunks = chunk_pages(
        [PageText(1, "abc")], chunk_size=1, overlap=0, respect_word_boundaries=False
    )

    assert [c.text for c in chunks] == ["a", "b", "c"]


# --------------------------------------------------------------------------- #
# Chunking: size and overlap behaviour
# --------------------------------------------------------------------------- #

UNBROKEN = "abcdefghij" * 50  # 500 characters, no whitespace


def test_chunks_respect_size_and_overlap_exactly_when_cutting_at_characters():
    chunks = chunk_pages(
        [PageText(1, UNBROKEN)], chunk_size=100, overlap=20, respect_word_boundaries=False
    )

    assert len(chunks) == 6
    assert all(len(c.text) <= 100 for c in chunks)
    for previous, current in zip(chunks, chunks[1:]):
        assert current.text[:20] == previous.text[-20:]


def test_chunks_cover_the_whole_text_without_gaps():
    chunks = chunk_pages(
        [PageText(1, UNBROKEN)], chunk_size=100, overlap=20, respect_word_boundaries=False
    )

    rebuilt = chunks[0].text + "".join(c.text[20:] for c in chunks[1:])
    assert rebuilt == UNBROKEN


def test_zero_overlap_gives_disjoint_chunks():
    chunks = chunk_pages(
        [PageText(1, UNBROKEN)], chunk_size=100, overlap=0, respect_word_boundaries=False
    )

    assert len(chunks) == 5
    assert "".join(c.text for c in chunks) == UNBROKEN


def test_chunk_indexes_are_sequential_and_chunks_are_unique():
    words = " ".join(f"word{i}" for i in range(400))

    chunks = chunk_pages([PageText(1, words)], chunk_size=100, overlap=20)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert len({c.text for c in chunks}) == len(chunks)


def test_word_boundaries_are_respected_by_default():
    valid_words = {f"word{i}" for i in range(400)}
    words = " ".join(f"word{i}" for i in range(400))

    chunks = chunk_pages([PageText(1, words)], chunk_size=100, overlap=20)

    seen: set[str] = set()
    for chunk in chunks:
        assert len(chunk.text) <= 100
        tokens = chunk.text.split()
        assert set(tokens) <= valid_words, f"cut mid-word in: {chunk.text!r}"
        seen.update(tokens)
    assert seen == valid_words  # nothing lost
    for previous, current in zip(chunks, chunks[1:]):
        assert current.text.split()[0] in previous.text.split()  # chunks do overlap


def test_long_unbroken_text_still_progresses_with_word_boundaries_on():
    text = "x" * 500

    with_boundaries = split_text_spans(text, 100, 20, respect_word_boundaries=True)
    without = split_text_spans(text, 100, 20, respect_word_boundaries=False)

    assert with_boundaries == without
    assert with_boundaries[-1][1] == 500


def test_maximum_overlap_terminates_and_makes_progress():
    text = "x" * 1000

    spans = split_text_spans(text, 50, 49, respect_word_boundaries=False)

    starts = [s for s, _ in spans]
    assert starts == sorted(set(starts))  # strictly increasing
    assert len(spans) == 951
    assert spans[-1][1] == 1000


def test_maximum_overlap_terminates_with_word_boundaries_on():
    text = " ".join(f"w{i}" for i in range(500))

    spans = split_text_spans(text, 50, 49)

    starts = [s for s, _ in spans]
    assert starts == sorted(set(starts))
    assert spans[-1][1] == len(text)


def test_default_settings_on_a_long_document():
    text = " ".join(f"sentence number {i}." for i in range(2000))

    chunks = chunk_pages([PageText(1, text)])

    assert len(chunks) > 1
    assert all(len(c.text) <= DEFAULT_CHUNK_SIZE for c in chunks)


# --------------------------------------------------------------------------- #
# Chunking: page metadata
# --------------------------------------------------------------------------- #


def test_chunk_spanning_pages_records_all_pages():
    pages = [PageText(1, "A" * 300), PageText(2, "B" * 300), PageText(3, "C" * 300)]

    chunks = chunk_pages(pages, chunk_size=200, overlap=0, respect_word_boundaries=False)

    assert [c.page_numbers for c in chunks] == [(1,), (1, 2), (2,), (2, 3), (3,)]
    assert [c.page_number for c in chunks] == [1, 1, 2, 2, 3]


def test_each_short_page_in_its_own_chunk_when_chunks_are_small():
    pages = [PageText(1, "A" * 100), PageText(2, "B" * 100)]

    chunks = chunk_pages(pages, chunk_size=102, overlap=0, respect_word_boundaries=False)

    assert chunks[0].page_numbers == (1,)
    assert chunks[-1].page_numbers[-1] == 2


def test_pages_without_text_never_appear_in_chunks():
    pages = [PageText(1, "A" * 100), PageText(2, ""), PageText(3, "C" * 100)]

    chunks = chunk_pages(pages)

    assert len(chunks) == 1
    assert chunks[0].page_numbers == (1, 3)


def test_original_page_numbers_are_kept_when_early_pages_are_blank():
    pages = [PageText(1, ""), PageText(2, ""), PageText(3, "content")]

    chunks = chunk_pages(pages)

    assert [(c.page_number, c.page_numbers) for c in chunks] == [(3, (3,))]


def test_end_to_end_extraction_then_chunking_keeps_page_numbers():
    pdf = make_pdf(["First page text.", "", "Third page text."])

    document = extract_pdf(pdf)
    chunks = chunk_pages(document.pages)

    assert len(chunks) == 1
    assert chunks[0].page_numbers == (1, 3)
    assert "First page text." in chunks[0].text
    assert "Third page text." in chunks[0].text


def test_chunk_pages_accepts_any_sequence_type():
    chunks = chunk_pages((PageText(1, "tuple input"),))

    assert chunks[0].text == "tuple input"


# --------------------------------------------------------------------------- #
# Invalid configuration
# --------------------------------------------------------------------------- #

BAD_CONFIGS = [
    (0, 0),
    (-5, 0),
    (100, -1),
    (100, 100),
    (100, 150),
    (100.5, 10),
    (100, 10.5),
    ("100", 10),
    (100, None),
    (True, 0),
]


@pytest.mark.parametrize("chunk_size, overlap", BAD_CONFIGS)
def test_invalid_config_raises_value_error_in_chunk_pages(chunk_size, overlap):
    with pytest.raises(ValueError):
        chunk_pages([PageText(1, "some text")], chunk_size=chunk_size, overlap=overlap)


@pytest.mark.parametrize("chunk_size, overlap", BAD_CONFIGS)
def test_invalid_config_raises_value_error_in_split_text_spans(chunk_size, overlap):
    with pytest.raises(ValueError):
        split_text_spans("some text", chunk_size, overlap)


def test_invalid_config_is_rejected_even_when_there_is_no_text():
    with pytest.raises(ValueError):
        chunk_pages([], chunk_size=100, overlap=100)


def test_overlap_error_message_mentions_both_values():
    with pytest.raises(ValueError, match=re.compile(r"overlap.*chunk_size", re.S)):
        chunk_pages([PageText(1, "text")], chunk_size=50, overlap=60)
