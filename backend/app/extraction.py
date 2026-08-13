"""PDF text extraction, per DESIGN.md's Extraction section: pypdf, run once
per upload, pages joined with `[Page N]` headings (1-indexed, matching the
PDF's own page numbers) so every downstream agent call can attribute a quote
back to the page it came from. No other markup — paragraph breaks are
whatever pypdf produces from the source PDF, not normalized or reflowed.

Checks run in the order DESIGN.md's Capacity map documents: upload size,
before Analyzer ever runs; then PDF validity; then whether any extractable
text exists at all (rejects scanned/image-only PDFs, no OCR in v1).
"""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB, per requirements.md; no separate page-count limit


class UploadValidationError(Exception):
    """error_code is one of "not_a_pdf" / "file_too_large" / "no_extractable_text",
    per DESIGN.md's API contract error set for POST /upload."""

    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


def extract_note_text(file_bytes: bytes) -> str:
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("file_too_large")

    try:
        reader = PdfReader(BytesIO(file_bytes))
        if len(reader.pages) == 0:
            raise UploadValidationError("not_a_pdf")
        page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    except PdfReadError:
        raise UploadValidationError("not_a_pdf")

    if not any(page_texts):
        raise UploadValidationError("no_extractable_text")

    sections = [f"[Page {i}]\n\n{text}" for i, text in enumerate(page_texts, start=1)]
    return "\n\n".join(sections)
