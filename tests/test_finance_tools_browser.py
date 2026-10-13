"""UI interaction checks; live API coverage is executed through ReqnRoll."""

import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from pydantic import TypeAdapter

from app.finance_calculations import CalculationInput, calculate
from app.finance_domain import load_domain_pack


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_domain_catalogue_and_calculation_ui():
    pw = pytest.importorskip("playwright.sync_api")
    root = Path(__file__).parents[1]
    static = root / "app/static"
    pack = load_domain_pack(root / "workspace/auto-finance-domain.toml")
    errors = []

    def route(request):
        path = urlparse(request.request.url).path
        if path == "/knowledge" or path.startswith("/static/"):
            file = static / (
                "knowledge.html" if path == "/knowledge" else path.removeprefix("/static/")
            )
            request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/finance/domain-pack":
            request.fulfill(json=pack.model_dump() | {"reference_only": True})
        elif path == "/api/finance/calculations":
            payload = TypeAdapter(CalculationInput).validate_python(
                json.loads(request.request.post_data)
            )
            request.fulfill(json=calculate(payload, pack))
        elif path == "/api/stlc":
            request.fulfill(json={})
        elif path == "/api/workspace/knowledge":
            request.fulfill(
                json={
                    "enabled": False,
                    "suite_count": 0,
                    "approved_output_count": 0,
                    "scenario_count": 0,
                    "suites": [],
                    "approved_outputs": [],
                }
            )
        else:
            request.fulfill(json={"display_name": "Reviewer", "is_admin": False})

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://finance.test/knowledge")
        pw.expect(page.locator("h1")).to_have_text("Saved outputs")
        pw.expect(page.locator(".graph-card")).to_be_hidden()
        pw.expect(page.locator(".finance-calculator")).to_be_hidden()
        page.locator(".nav-parent", has_text="Auto finance").click()
        page.get_by_role("link", name="Project knowledge & rules", exact=True).click()
        pw.expect(page.locator("h1")).to_have_text("Project knowledge & rules")
        pw.expect(page.locator(".finance-calculator")).to_be_hidden()
        pw.expect(page.locator('a[aria-current="page"]')).to_have_text("Project knowledge & rules")
        pw.expect(page.locator("#finance-products li")).to_have_count(7)
        pw.expect(page.locator("#finance-journeys li")).to_have_count(7)
        page.locator(".nav-parent", has_text="Knowledge").click()
        page.get_by_role("link", name="Knowledge graph", exact=True).click()
        pw.expect(page.locator("h1")).to_have_text("Knowledge graph")
        pw.expect(page.locator("#finance-products")).to_be_hidden()
        pw.expect(page.locator(".graph-node")).to_have_count(15)
        pw.expect(page.locator("#graph-source")).to_have_value("live")
        page.locator(".nav-parent", has_text="Auto finance").click()
        page.get_by_role("link", name="Calculation checks", exact=True).click()
        pw.expect(page.locator("h1")).to_have_text("Calculation checks")
        pw.expect(page.locator(".graph-card")).to_be_hidden()
        page.fill("#finance-input-principal", "12000")
        page.fill("#finance-input-annual_nominal_rate", "0")
        page.fill("#finance-input-payments", "12")
        page.fill("#finance-observed", "999.99")
        page.click("#finance-calculate")
        pw.expect(page.locator("#finance-calc-status")).to_contain_text("does not match")
        pw.expect(page.locator("#finance-calc-values")).to_contain_text("1000.00")
        pw.expect(page.locator("#finance-calc-checks")).to_contain_text("difference -0.01")
        page.select_option("#finance-calc-kind", "vat")
        page.fill("#finance-input-net", "100")
        page.fill("#finance-input-vat_rate", "20")
        page.fill("#finance-observed", "120")
        page.click("#finance-calculate")
        pw.expect(page.locator("#finance-calc-status")).to_have_text("Observed value matches.")
        pw.expect(page.locator("#finance-calc-values")).to_contain_text("GBP 120.00")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.locator("#sidebar-toggle").click()
        pw.expect(page.locator(".nav-parent", has_text="Auto finance")).to_have_attribute(
            "aria-expanded", "true"
        )
        pw.expect(page.get_by_role("link", name="Calculation checks", exact=True)).to_be_visible()
        page.keyboard.press("Escape")
        pw.expect(page.locator("#sidebar-toggle")).to_have_attribute("aria-expanded", "false")
        assert not errors, errors
        page.click("#finance-use-calculation")
        pw.expect(page).to_have_url("http://finance.test/#test-studio")
        staged = page.evaluate(
            "JSON.parse(sessionStorage.getItem('finance-reference-calculation'))"
        )
        assert staged["kind"] == "vat" and staged["net"] == "100"
        assert "result" not in staged
        browser.close()
