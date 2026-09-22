"""The proposed BRD is exported as readable PDF text."""

from io import BytesIO

from pypdf import PdfReader

from app.pdf_exporter import brd_draft_to_pdf


def test_brd_draft_pdf_contains_preview_edits_and_paginates():
    text = "# Proposed BRD revision\n\n## Extracted requirements\n" + (
        "The quotation must reject a negative deposit.\n" * 120
    ) + "## Validation review notes\nReviewed correction approved for discussion."
    payload = brd_draft_to_pdf(text)

    assert payload.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(payload))
    assert len(reader.pages) > 1
    extracted = "\n".join(page.extract_text() for page in reader.pages)
    assert "The quotation must reject a negative deposit." in extracted
    assert "Reviewed correction approved for discussion." in extracted
