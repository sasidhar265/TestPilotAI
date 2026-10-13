"""Bounded real-browser journeys with explicit actions and observed navigation metrics."""

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Utilities"))
from PerformanceReportUtility import report

root = Path(__file__).resolve().parents[1]
config = json.loads((root / "Input/PerformanceConfig.Json").read_text())
checks = json.loads((root / "Input/TestData.Json").read_text())
target = os.environ.get("TARGET_BASE_URL", "").rstrip("/")
parsed = urlparse(target)
if (
    parsed.scheme not in ("http", "https")
    or not parsed.hostname
    or parsed.path not in ("", "/")
    or parsed.username
    or parsed.query
):
    sys.exit("Set TARGET_BASE_URL to the actual HTTP(S) origin without credentials or a path.")
run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
output = root / "TestResults/Reports" / run_id
samples = []


async def user(browser, identifier, started):
    await asyncio.sleep(identifier * config["ramp_seconds"] / config["threads"])
    options = {"viewport": {"width": 1440, "height": 900}}
    if os.environ.get("BROWSER_STORAGE_STATE"):
        options["storage_state"] = os.environ["BROWSER_STORAGE_STATE"]
    context = await browser.new_context(**options)
    page = await context.new_page()
    page.set_default_timeout(config["timeout_ms"])
    for iteration in range(config["iterations"]):
        for check in checks:
            errors = []

            def on_error(error, captured=errors):
                captured.append(str(error))

            def on_response(response, captured=errors):
                if response.status >= 400:
                    captured.append("HTTP error response")

            def on_request_failed(request, captured=errors):
                captured.append("Network request failed")

            page.on("pageerror", on_error)
            page.on("response", on_response)
            page.on("requestfailed", on_request_failed)
            action_timings = []
            start = time.time() * 1000
            began = time.perf_counter()
            success = False
            metrics = None
            failure = None
            try:
                response = await page.goto(target + check["path"], wait_until="load")
                if response is None or response.status != check["expected_status"]:
                    raise RuntimeError("Unexpected navigation response status")
                for action in check["actions"]:
                    action_start = time.perf_counter()
                    locator = page.locator(action["selector"])
                    if action["action"] == "click":
                        await locator.click()
                    elif action["action"] == "fill":
                        value = (
                            os.environ[action["value_env"]]
                            if action.get("value_env")
                            else action["value"]
                        )
                        await locator.fill(value)
                    elif action["action"] == "select":
                        await locator.select_option(action["value"])
                    else:
                        await locator.wait_for(state="visible")
                    action_timings.append(
                        {
                            "action": action["action"],
                            "elapsed_ms": (time.perf_counter() - action_start) * 1000,
                        }
                    )
                await page.locator(check["ready_selector"]).wait_for(state="visible")
                metrics = await page.evaluate("""() => {
                  const n = performance.getEntriesByType('navigation')[0];
                  const fcp = performance.getEntriesByName('first-contentful-paint')[0];
                  return {ttfb_ms:n?.responseStart,
                    dom_content_loaded_ms:n?.domContentLoadedEventEnd,
                    load_ms:n?.loadEventEnd, fcp_ms:fcp?.startTime ?? null};
                }""")
                success = not errors
            except Exception as error:
                failure = type(error).__name__
            finally:
                page.remove_listener("pageerror", on_error)
                page.remove_listener("response", on_response)
                page.remove_listener("requestfailed", on_request_failed)
            elapsed = (time.perf_counter() - began) * 1000
            if elapsed > check["max_response_ms"]:
                failure = "JourneyDurationBudgetExceeded"
            success = success and elapsed <= check["max_response_ms"]
            samples.append(
                {
                    "case_id": check["case_id"],
                    "user": identifier,
                    "iteration": iteration,
                    "start_ms": start,
                    "end_ms": time.time() * 1000,
                    "elapsed_ms": elapsed,
                    "success": success,
                    "failure": failure,
                    "browser_error_count": len(errors),
                    "navigation_metrics": metrics,
                    "action_timings": action_timings,
                    "warmup": start < started + config["warmup_seconds"] * 1000,
                }
            )
            await asyncio.sleep(config["think_time_ms"] / 1000)
    await context.close()


async def main():
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch()
        try:
            await asyncio.gather(
                *(
                    user(browser, identifier, time.time() * 1000)
                    for identifier in range(config["threads"])
                )
            )
        finally:
            await browser.close()


if __name__ == "__main__":
    infrastructure_failure = None
    try:
        asyncio.run(main())
    except Exception as error:
        infrastructure_failure = type(error).__name__
    passed = report(
        samples,
        config,
        output,
        {
            "run_id": run_id,
            "tool": "Playwright Chromium",
            "target": target,
            "infrastructure_failure": infrastructure_failure,
        },
    )
    print("Results:", output / "report.html")
    sys.exit(0 if passed and infrastructure_failure is None else 1)
