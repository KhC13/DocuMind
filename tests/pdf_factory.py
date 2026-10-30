"""Helpers that build small PDFs in memory for tests.

``make_pdf`` writes a minimal but valid PDF by hand (Helvetica text, one content
stream per page), so the tests need no extra dependency and no binary fixtures.
"""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(page_texts: list[str]) -> bytes:
    """Build a PDF with one page per string. An empty string gives a blank page.

    A ``\\n`` inside a string starts a new line on the same page.
    """
    count = len(page_texts)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(count))
    objects: dict[int, str] = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {count} >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i, text in enumerate(page_texts):
        page_no, content_no = 4 + 2 * i, 5 + 2 * i
        if text:
            lines = [f"({_escape(line)}) Tj" for line in text.split("\n")]
            stream = "BT /F1 12 Tf 14 TL 72 720 Td " + " T* ".join(lines) + " ET"
        else:
            stream = ""
        objects[page_no] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_no} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        )
        objects[content_no] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n{objects[number]}\nendobj\n".encode("latin-1")

    xref_offset = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode("latin-1")
    for number in sorted(objects):
        out += f"{offsets[number]:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)


def encrypt_pdf(
    pdf_bytes: bytes,
    user_password: str,
    owner_password: str | None = None,
    algorithm: str = "AES-256",
) -> bytes:
    """Return an encrypted copy of ``pdf_bytes``."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes)))
    writer.encrypt(user_password, owner_password, algorithm=algorithm)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
