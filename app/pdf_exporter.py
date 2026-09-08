"""Create paginated, searchable PDF reports from the canonical test suite."""

import io
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Flowable, Paragraph, SimpleDocTemplate, Spacer

from app.models import TestSuite

pdfmetrics.registerFont(
    TTFont("SuiteReport", str(Path(reportlab.__file__).parent / "fonts/Vera.ttf"))
)


def suite_to_pdf(suite: TestSuite) -> bytes:
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "SuiteReport"
    body = ParagraphStyle("SuiteBody", parent=styles["BodyText"], leading=15, spaceAfter=6)
    story: list[Flowable] = []

    def paragraph(text: str, style: ParagraphStyle = body) -> None:
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), style))

    paragraph(suite.feature_name, styles["Title"])
    paragraph(f"Generated test suite | {len(suite.test_cases)} test cases")
    for case in suite.test_cases:
        story.append(Spacer(1, 12))
        paragraph(f"{case.id} — {case.title}", styles["Heading2"])
        paragraph(f"{case.execution_mode.value} | {case.category.value} | {case.priority}")
        paragraph(f"Scenario group: {case.scenario_group}")
        paragraph(f"Objective: {case.objective}")
        paragraph(f"Feasibility: {case.feasibility_reason}")
        if case.preconditions:
            paragraph("Preconditions: " + "; ".join(case.preconditions))
        for index, step in enumerate(case.steps, 1):
            paragraph(f"Step {index}: {step.action}")
            paragraph(f"Expected result: {step.expected_result}")
        if case.test_data:
            paragraph("Test data", styles["Heading3"])
            for datum in case.test_data:
                paragraph(f"{datum.name}: {datum.value} ({datum.purpose})")
        if case.gherkin:
            paragraph("Gherkin", styles["Heading3"])
            paragraph(case.gherkin)
        if case.acceptance_criteria_covered:
            paragraph("Requirements: " + ", ".join(case.acceptance_criteria_covered))
        if case.tags:
            paragraph("Tags: " + ", ".join(case.tags))
    for title, notes in [("Assumptions", suite.assumptions), ("Coverage", suite.coverage_notes)]:
        if notes:
            paragraph(title, styles["Heading2"])
            for note in notes:
                paragraph(note)

    def footer(canvas: Canvas, document: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont("SuiteReport", 9)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(A4[0] - 42, 25, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=42,
        bottomMargin=42,
        title=suite.feature_name,
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
