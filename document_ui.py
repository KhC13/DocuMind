"""Streamlit interface for PDF upload and document processing (Phase 2).

This section works independently of the Gemini chat: it needs no API key and
makes no network calls. Results are kept in ``st.session_state`` so they survive
the reruns Streamlit triggers whenever the user chats.
"""

from __future__ import annotations

import math
from typing import Sequence

import streamlit as st

from document_processor import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    MAX_FILE_SIZE_MB,
    DocumentProcessingError,
    ExtractedDocument,
    chunk_pages,
    extract_pdf,
    validate_file_size,
)

_STATE_KEY = "document_result"
PREVIEW_CHARS = 3000
CHUNKS_PER_PAGE = 10
_MAX_LISTED_PAGES = 15


def format_pages(page_numbers: Sequence[int]) -> str:
    """Human-readable page label, e.g. ``page 3``, ``pages 3-4``, ``pages 3, 5``."""
    pages = list(page_numbers)
    if not pages:
        return "no page"
    if len(pages) == 1:
        return f"page {pages[0]}"
    if pages == list(range(pages[0], pages[-1] + 1)):
        return f"pages {pages[0]}-{pages[-1]}"
    return "pages " + ", ".join(str(p) for p in pages)


def build_preview(document: ExtractedDocument, limit: int = PREVIEW_CHARS) -> tuple[str, bool]:
    """Return ``(preview_text, was_truncated)`` with page markers between pages."""
    parts = [f"--- Page {p.page_number} ---\n{p.text}" for p in document.pages if p.text]
    full = "\n\n".join(parts)
    if len(full) <= limit:
        return full, False
    return full[:limit], True


def _file_key(uploaded) -> object:
    """Identify an uploaded file across reruns."""
    return getattr(uploaded, "file_id", None) or (uploaded.name, uploaded.size)


def _process(uploaded, chunk_size: int, overlap: int) -> None:
    """Extract and chunk the uploaded PDF, storing the result in session state."""
    with st.spinner("Extracting text and creating chunks..."):
        try:
            document = extract_pdf(uploaded.getvalue(), uploaded.name)
            chunks = chunk_pages(document.pages, chunk_size, overlap)
        except DocumentProcessingError as exc:
            st.session_state.pop(_STATE_KEY, None)
            st.error(str(exc))
            return
        except ValueError as exc:
            st.session_state.pop(_STATE_KEY, None)
            st.error(f"Invalid chunking settings: {exc}")
            return
        except Exception as exc:  # last resort: never crash the whole app
            st.session_state.pop(_STATE_KEY, None)
            st.error(f"Unexpected error while processing the PDF ({type(exc).__name__}): {exc}")
            return

    previous = st.session_state.get(_STATE_KEY)
    st.session_state[_STATE_KEY] = {
        "file_key": _file_key(uploaded),
        "document": document,
        "chunks": chunks,
        "chunk_size": chunk_size,
        "overlap": overlap,
        "version": (previous["version"] + 1) if previous else 1,
    }


def _render_results(result: dict) -> None:
    document: ExtractedDocument = result["document"]
    chunks = result["chunks"]
    version = result["version"]

    columns = st.columns(4)
    columns[0].metric("Pages", document.page_count)
    columns[1].metric("Characters", f"{document.char_count:,}")
    columns[2].metric("Chunks", len(chunks))
    columns[3].metric("Pages without text", len(document.empty_pages))

    if not document.has_text:
        st.warning(
            "No extractable text was found. This PDF is probably a scan or contains "
            "only images. This version does not include OCR (text recognition for "
            "images), so it cannot read such documents. Try a PDF with selectable text."
        )
        return

    if document.failed_pages:
        st.warning(
            f"Text extraction failed on {format_pages(document.failed_pages[:_MAX_LISTED_PAGES])}"
            f"{' and more' if len(document.failed_pages) > _MAX_LISTED_PAGES else ''}. "
            "Those pages were skipped."
        )
    other_empty = [p for p in document.empty_pages if p not in document.failed_pages]
    if other_empty:
        st.warning(
            f"{len(other_empty)} page(s) have no extractable text "
            f"({format_pages(other_empty[:_MAX_LISTED_PAGES])}"
            f"{', ...' if len(other_empty) > _MAX_LISTED_PAGES else ''}). "
            "They may be scanned images or blank; they are skipped."
        )

    st.success(
        f"Processed with chunk size {result['chunk_size']} and overlap {result['overlap']}."
    )

    with st.expander("Preview extracted text"):
        preview, truncated = build_preview(document)
        st.text_area(
            "Extracted text",
            value=preview,
            height=300,
            disabled=True,
            label_visibility="collapsed",
            key=f"preview_{version}",
        )
        if truncated:
            st.caption(
                f"Preview truncated: showing the first {PREVIEW_CHARS:,} of "
                f"{document.char_count:,} characters."
            )

    with st.expander(f"Inspect chunks ({len(chunks)})"):
        if not chunks:
            st.write("No chunks were generated.")
            return
        total_pages = math.ceil(len(chunks) / CHUNKS_PER_PAGE)
        current = 1
        if total_pages > 1:
            current = st.number_input(
                f"Chunk page (of {total_pages}, {CHUNKS_PER_PAGE} chunks each)",
                min_value=1,
                max_value=total_pages,
                value=1,
                step=1,
                key=f"chunk_page_{version}",
            )
        first = (int(current) - 1) * CHUNKS_PER_PAGE
        for chunk in chunks[first : first + CHUNKS_PER_PAGE]:
            st.caption(
                f"Chunk {chunk.chunk_index} - {format_pages(chunk.page_numbers)} - "
                f"{len(chunk.text)} characters"
            )
            st.text_area(
                f"Chunk {chunk.chunk_index}",
                value=chunk.text,
                height=150,
                disabled=True,
                label_visibility="collapsed",
                key=f"chunk_{version}_{chunk.chunk_index}",
            )


def render_document_section() -> None:
    """Render the upload / process / inspect section of the page."""
    with st.container(border=True):
        st.subheader("📄 Document processing")
        st.caption(
            f"Upload a PDF (up to {MAX_FILE_SIZE_MB} MB) to extract its text and split it "
            "into chunks. This step runs locally and does not use Gemini."
        )

        uploaded = st.file_uploader(
            "Upload a PDF",
            type=["pdf"],
            accept_multiple_files=False,
            key="pdf_uploader",
        )

        if uploaded is None:
            st.session_state.pop(_STATE_KEY, None)
            return

        try:
            validate_file_size(uploaded.size)
        except DocumentProcessingError as exc:
            st.session_state.pop(_STATE_KEY, None)
            st.error(str(exc))
            return

        st.write(f"**{uploaded.name}** - {uploaded.size / 1024:,.1f} KB")

        with st.expander("Chunking settings"):
            chunk_size = st.number_input(
                "Chunk size (characters)",
                min_value=100,
                max_value=10000,
                value=DEFAULT_CHUNK_SIZE,
                step=50,
            )
            overlap = st.number_input(
                "Overlap between chunks (characters)",
                min_value=0,
                max_value=5000,
                value=DEFAULT_CHUNK_OVERLAP,
                step=10,
            )
        settings_valid = overlap < chunk_size
        if not settings_valid:
            st.error("Overlap must be smaller than the chunk size. Adjust the chunking settings.")

        result = st.session_state.get(_STATE_KEY)
        is_current = bool(result) and result["file_key"] == _file_key(uploaded)
        if result and not is_current:
            st.session_state.pop(_STATE_KEY, None)
            result = None

        label = "Reprocess PDF" if is_current else "Process PDF"
        clicked = st.button(label, type="primary", disabled=not settings_valid)
        if clicked:
            _process(uploaded, int(chunk_size), int(overlap))
            result = st.session_state.get(_STATE_KEY)
            if result:
                # Rerun so the button label (chosen above, before processing)
                # changes to "Reprocess PDF". On failure we skip this so the
                # error message stays on screen.
                st.rerun()

        if result:
            _render_results(result)
        elif not clicked:
            st.info("Press **Process PDF** to extract the text.")
