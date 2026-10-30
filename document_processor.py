"""PDF validation, page-by-page text extraction, and text chunking.

This module is deliberately independent of Streamlit and of the Gemini API, so
it can be tested on its own and reused later (e.g. for embeddings and RAG).

Typical use::

    document = extract_pdf(pdf_bytes, filename="report.pdf")
    chunks = chunk_pages(document.pages, chunk_size=1000, overlap=150)

Chunk page-number strategy
--------------------------
Chunks are cut from one continuous text stream built by joining the text of all
pages with a blank line, so a chunk may cross a page boundary. Every ``Chunk``
therefore records:

* ``page_numbers`` - every page that contributed text to the chunk, and
* ``page_number``  - the first of those pages (a convenient single value).

Text that appears only through the *overlap* with the previous chunk counts as
belonging to the chunk, so an overlap can add the previous page to
``page_numbers``. Pages with no extractable text never appear in any chunk.
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field
from typing import Sequence

from pypdf import PdfReader
from pypdf import errors as pypdf_errors

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

PAGE_SEPARATOR = "\n\n"
_PDF_MAGIC = b"%PDF-"
# Fraction of a chunk (measured from its end) in which we look for a
# whitespace position to cut at, when respecting word boundaries.
_BOUNDARY_SEARCH_FRACTION = 0.2


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class DocumentProcessingError(Exception):
    """Base class for all expected document-processing failures.

    The message is written to be shown directly to the end user.
    """


class InvalidFileError(DocumentProcessingError):
    """The file is not a PDF (wrong extension or missing PDF header)."""


class EmptyFileError(DocumentProcessingError):
    """The file contains no data."""


class FileTooLargeError(DocumentProcessingError):
    """The file exceeds the maximum allowed upload size."""


class EncryptedPDFError(DocumentProcessingError):
    """The PDF is password-protected or encrypted in a way we cannot open."""


class CorruptedPDFError(DocumentProcessingError):
    """The PDF is damaged, truncated, or otherwise unreadable."""


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PageText:
    """Text extracted from a single PDF page (``page_number`` is 1-based)."""

    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    """Result of extracting a PDF.

    ``pages`` contains *every* page of the PDF, including pages with no
    extractable text (their ``text`` is an empty string), so page numbers are
    always preserved.
    """

    filename: str
    pages: list[PageText]
    failed_pages: list[int] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def char_count(self) -> int:
        return sum(len(page.text) for page in self.pages)

    @property
    def has_text(self) -> bool:
        return self.char_count > 0

    @property
    def empty_pages(self) -> list[int]:
        """Page numbers with no extractable text."""
        return [page.page_number for page in self.pages if not page.text]


@dataclass(frozen=True)
class Chunk:
    """A piece of document text with its page metadata.

    ``page_number`` is the first page the chunk touches; ``page_numbers`` lists
    all pages it touches, in order (see the module docstring).
    """

    text: str
    page_number: int
    chunk_index: int
    page_numbers: tuple[int, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["page_numbers"] = list(self.page_numbers)
        return data


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def validate_pdf_upload(
    file_bytes: bytes,
    filename: str = "document.pdf",
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> None:
    """Cheap checks done before attempting to parse. Raises on failure."""
    validate_file_size(len(file_bytes), max_size_bytes)

    if not filename.lower().endswith(".pdf"):
        raise InvalidFileError(
            f"'{filename}' is not a PDF file. Please upload a file ending in .pdf."
        )
    if not file_bytes:
        raise EmptyFileError("The uploaded file is empty (0 bytes).")
    # The spec allows a few bytes of junk before the header, so check the start.
    if _PDF_MAGIC not in file_bytes[:1024]:
        raise InvalidFileError(
            f"'{filename}' does not look like a valid PDF (missing PDF header)."
        )


def validate_file_size(size_bytes: int, max_size_bytes: int = MAX_FILE_SIZE_BYTES) -> None:
    """Raise ``FileTooLargeError`` if ``size_bytes`` exceeds the limit."""
    if size_bytes > max_size_bytes:
        raise FileTooLargeError(
            f"The file is {size_bytes / (1024 * 1024):.1f} MB, which is larger than "
            f"the {max_size_bytes / (1024 * 1024):g} MB limit. "
            "Please upload a smaller PDF."
        )


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


def _clean_page_text(raw: str) -> str:
    """Normalise line endings, drop NUL characters, trim outer whitespace."""
    return raw.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()


def extract_pdf(
    file_bytes: bytes,
    filename: str = "document.pdf",
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> ExtractedDocument:
    """Extract text from a PDF, page by page.

    Raises a ``DocumentProcessingError`` subclass with a user-friendly message if
    the file is invalid, too large, empty, encrypted, or unreadable. A PDF that
    opens fine but has no text layer (e.g. a scan) is *not* an error: the result
    simply has ``has_text == False``.
    """
    validate_pdf_upload(file_bytes, filename, max_size_bytes)

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except pypdf_errors.EmptyFileError as exc:
        raise EmptyFileError("The uploaded file is empty.") from exc
    except Exception as exc:  # pypdf raises several unrelated error types
        raise CorruptedPDFError(
            "This PDF could not be opened. It may be corrupted or incomplete."
        ) from exc

    if reader.is_encrypted:
        _try_open_encrypted(reader)

    try:
        raw_pages = list(reader.pages)
    except Exception as exc:
        raise CorruptedPDFError(
            "This PDF's page structure could not be read. It may be corrupted."
        ) from exc

    if not raw_pages:
        raise CorruptedPDFError("This PDF contains no pages.")

    pages: list[PageText] = []
    failed_pages: list[int] = []
    for number, page in enumerate(raw_pages, start=1):
        try:
            text = _clean_page_text(page.extract_text() or "")
        except Exception:
            # One bad page should not lose the whole document.
            text = ""
            failed_pages.append(number)
        pages.append(PageText(page_number=number, text=text))

    if len(failed_pages) == len(pages):
        raise CorruptedPDFError(
            "Text could not be read from any page. The PDF may be corrupted."
        )

    return ExtractedDocument(filename=filename, pages=pages, failed_pages=failed_pages)


def _try_open_encrypted(reader: PdfReader) -> None:
    """Try an empty password; raise ``EncryptedPDFError`` if that does not work."""
    message = (
        "This PDF is password-protected or encrypted, so its text cannot be read. "
        "Remove the password and upload it again."
    )
    try:
        opened = reader.decrypt("")
    except Exception as exc:  # includes pypdf's DependencyError for AES
        raise EncryptedPDFError(message) from exc
    if not opened:
        raise EncryptedPDFError(message)


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #


def _validate_chunk_config(chunk_size: int, overlap: int) -> None:
    for name, value in (("chunk_size", chunk_size), ("overlap", overlap)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer, got {value!r}.")
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be greater than 0, got {chunk_size}.")
    if overlap < 0:
        raise ValueError(f"overlap must not be negative, got {overlap}.")
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be smaller than chunk_size ({chunk_size})."
        )


def split_text_spans(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    respect_word_boundaries: bool = True,
) -> list[tuple[int, int]]:
    """Return ``(start, end)`` character spans that cover ``text``.

    Each span is at most ``chunk_size`` characters. Consecutive spans overlap by
    about ``overlap`` characters. With ``respect_word_boundaries`` (default),
    spans end at whitespace where possible and start at the beginning of a
    word, so the real overlap can be slightly smaller than requested; with it
    off, spans are cut at exact character positions.

    Progress is guaranteed: because ``overlap < chunk_size`` and every span must
    extend past ``start + overlap``, each new span starts strictly after the
    previous start, so the loop always terminates.
    """
    _validate_chunk_config(chunk_size, overlap)

    length = len(text)
    spans: list[tuple[int, int]] = []
    start = 0
    while start < length:
        end = min(start + chunk_size, length)

        if respect_word_boundaries and end < length:
            window_start = max(start + overlap + 1, end - int(chunk_size * _BOUNDARY_SEARCH_FRACTION))
            cut = max(text.rfind(" ", window_start, end), text.rfind("\n", window_start, end))
            if cut != -1:
                end = cut + 1  # keep the whitespace character with this chunk

        spans.append((start, end))
        if end >= length:
            break

        next_start = end - overlap
        if respect_word_boundaries and overlap > 0:
            # Prefer starting the next chunk at the beginning of a word. If the
            # overlap region has no whitespace at all (a long URL, or languages
            # written without spaces), keep the exact cut so the overlap is not lost.
            boundary = next_start
            while boundary < end and not text[boundary - 1].isspace():
                boundary += 1
            if boundary < end:
                next_start = boundary
        start = next_start

    return spans


def chunk_pages(
    pages: Sequence[PageText],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    respect_word_boundaries: bool = True,
) -> list[Chunk]:
    """Split page texts into overlapping chunks that keep page metadata.

    Returns an empty list when there is no text. A document shorter than
    ``chunk_size`` yields a single chunk. Raises ``ValueError`` for an invalid
    ``chunk_size``/``overlap`` combination (even if there is no text).
    """
    _validate_chunk_config(chunk_size, overlap)

    # Build one text stream, remembering which character range belongs to which page.
    parts: list[str] = []
    page_ranges: list[tuple[int, int, int]] = []  # (page_number, start, end)
    position = 0
    for page in pages:
        if not page.text.strip():
            continue
        if parts:
            position += len(PAGE_SEPARATOR)
        page_ranges.append((page.page_number, position, position + len(page.text)))
        parts.append(page.text)
        position += len(page.text)
    full_text = PAGE_SEPARATOR.join(parts)

    chunks: list[Chunk] = []
    for start, end in split_text_spans(full_text, chunk_size, overlap, respect_word_boundaries):
        raw = full_text[start:end]
        stripped = raw.strip()
        if not stripped:
            continue
        # Page lookup should use the visible text, not leading/trailing whitespace.
        visible_start = start + (len(raw) - len(raw.lstrip()))
        visible_end = end - (len(raw) - len(raw.rstrip()))
        touched = tuple(
            number
            for number, page_start, page_end in page_ranges
            if page_start < visible_end and page_end > visible_start
        )
        chunks.append(
            Chunk(
                text=stripped,
                page_number=touched[0],
                chunk_index=len(chunks),
                page_numbers=touched,
            )
        )
    return chunks
