"""Build traceable performance and database checks from explicit case inputs."""

import io
import json
import re
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.agents.implementation_approval import require_implementation_approval
from app.agents.multilanguage_agent import ArtifactFile
from app.agents.reqnroll_step_definition_agent import StepDefinitionRequest
from app.quotation_contract import PAYLOAD_PATH, quotation_feature

router = APIRouter(prefix="/api/script-packs", tags=["script-packs"])


class HttpCheck(BaseModel):
    case_id: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    path: str = Field(min_length=1, max_length=4000)
    body: str = Field(default="", max_length=100_000)
    content_type: str = Field(default="application/json", max_length=200)
    headers: dict[str, str] = Field(default_factory=dict, max_length=50)
    expected_status: int = Field(ge=100, le=599)
    max_response_ms: int = Field(gt=0, le=3_600_000)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or "\n" in value or "\r" in value:
            raise ValueError("Supply a relative HTTP path beginning with a single /.")
        return value


class DatabaseCheck(BaseModel):
    case_id: str
    query: str = Field(min_length=6, max_length=30_000)
    expected_rows: int = Field(ge=0, le=2_147_483_647)

    @field_validator("query")
    @classmethod
    def select_query(cls, value: str) -> str:
        value = value.strip().removesuffix(";").rstrip()
        # This is a limited query shape check, not an SQL security sandbox.
        if not re.match(r"SELECT\s", value, re.I) or ";" in value or "--" in value or "/*" in value:
            raise ValueError("Supply one SELECT query without comments or internal semicolons.")
        if re.search(r"\b(INTO|FOR\s+UPDATE)\b", value, re.I):
            raise ValueError("SELECT INTO and FOR UPDATE are not supported in database checks.")
        return value


class BrowserAction(BaseModel):
    action: Literal["click", "fill", "select", "wait_visible"]
    selector: str = Field(min_length=1, max_length=2000)
    value: str = Field(default="", max_length=10000)
    value_env: str = Field(default="", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$|^$")


class BrowserCheck(BaseModel):
    case_id: str
    path: str = Field(min_length=1, max_length=4000)
    ready_selector: str = Field(min_length=1, max_length=2000)
    actions: list[BrowserAction] = Field(default_factory=list, max_length=50)
    expected_status: int = Field(default=200, ge=100, le=599)
    max_response_ms: int = Field(gt=0, le=3600000)

    _relative_path = field_validator("path")(HttpCheck.relative_path.__func__)


class ScriptPackRequest(StepDefinitionRequest):
    target: Literal["jmeter", "browser", "sql", "oracle"]
    http_checks: list[HttpCheck] = Field(default_factory=list, max_length=100)
    browser_checks: list[BrowserCheck] = Field(default_factory=list, max_length=100)
    database_checks: list[DatabaseCheck] = Field(default_factory=list, max_length=100)
    threads: int = Field(default=1, ge=1, le=10000)
    ramp_seconds: int = Field(default=1, ge=1, le=86400)
    iterations: int = Field(default=1, ge=1, le=1000000)
    think_time_ms: int = Field(default=0, ge=0, le=3600000)
    warmup_seconds: int = Field(default=0, ge=0, le=86400)
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    p95_ms: int | None = Field(default=None, gt=0, le=3600000)
    p99_ms: int | None = Field(default=None, gt=0, le=3600000)
    max_error_percent: float = Field(default=0, ge=0, le=100)
    min_samples: int = Field(default=1, ge=1, le=10000000)
    timeout_ms: int = Field(default=30000, ge=1, le=3600000)


class ScriptPack(BaseModel):
    target: str
    files: list[ArtifactFile]
    case_ids: list[str]
    notes: list[str]


def prop(parent: ET.Element, name: str, value: str | int, kind: str = "stringProp") -> None:
    ET.SubElement(parent, kind, name=name).text = str(value)


def node(parent: ET.Element, kind: str, name: str, gui: str) -> tuple[ET.Element, ET.Element]:
    item = ET.SubElement(parent, kind, testname=name, testclass=kind, guiclass=gui, enabled="true")
    return item, ET.SubElement(parent, "hashTree")


def jmeter_plan(request: ScriptPackRequest) -> str:
    root = ET.Element("jmeterTestPlan", version="1.2", properties="5.0", jmeter="5.6.3")
    tree = ET.SubElement(root, "hashTree")
    plan, tree = node(tree, "TestPlan", request.suite.feature_name, "TestPlanGui")
    ET.SubElement(
        plan, "elementProp", name="TestPlan.user_defined_variables", elementType="Arguments"
    )
    group, tree = node(tree, "ThreadGroup", "Approved case workload", "ThreadGroupGui")
    prop(group, "ThreadGroup.on_sample_error", "continue")
    for name, setting in (("num_threads", request.threads), ("ramp_time", request.ramp_seconds)):
        prop(group, "ThreadGroup." + name, setting)
    loop = ET.SubElement(
        group,
        "elementProp",
        name="ThreadGroup.main_controller",
        elementType="LoopController",
        guiclass="LoopControlPanel",
        testclass="LoopController",
        enabled="true",
    )
    prop(loop, "LoopController.continue_forever", "false", "boolProp")
    prop(loop, "LoopController.loops", request.iterations)
    if request.duration_seconds:
        prop(group, "ThreadGroup.scheduler", "true", "boolProp")
        prop(group, "ThreadGroup.duration", request.duration_seconds)
        loop.find("stringProp[@name='LoopController.loops']").text = "-1"
    cookies, _ = node(tree, "CookieManager", "Per-user cookies", "CookiePanel")
    ET.SubElement(cookies, "collectionProp", name="CookieManager.cookies")
    prop(cookies, "CookieManager.clearEachIteration", "false", "boolProp")
    if request.think_time_ms:
        timer, _ = node(tree, "ConstantTimer", "Request pacing", "ConstantTimerGui")
        prop(timer, "ConstantTimer.delay", request.think_time_ms)
    for index, check in enumerate(request.http_checks, 1):
        sampler, children = node(tree, "HTTPSamplerProxy", check.case_id, "HttpTestSampleGui")
        for key, value in {
            "domain": "${__P(host,)}",
            "port": "${__P(port,)}",
            "protocol": "${__P(protocol,https)}",
            "path": check.path,
            "method": check.method,
            "contentEncoding": "UTF-8",
            "connect_timeout": "${__P(connect_timeout,10000)}",
            "response_timeout": "${__P(response_timeout,30000)}",
        }.items():
            prop(sampler, "HTTPSampler." + key, value)
        prop(sampler, "HTTPSampler.follow_redirects", "false", "boolProp")
        prop(sampler, "HTTPSampler.use_keepalive", "true", "boolProp")
        prop(sampler, "HTTPSampler.postBodyRaw", "true", "boolProp")
        args = ET.SubElement(
            sampler, "elementProp", name="HTTPsampler.Arguments", elementType="Arguments"
        )
        collection = ET.SubElement(args, "collectionProp", name="Arguments.arguments")
        if check.body:
            arg = ET.SubElement(collection, "elementProp", name="", elementType="HTTPArgument")
            prop(arg, "HTTPArgument.always_encode", "false", "boolProp")
            prop(arg, "Argument.value", f"${{__FileToString(Input/body-{index:03d}.txt,UTF-8,)}}")
            prop(arg, "Argument.metadata", "=")
        headers, _ = node(children, "HeaderManager", "Request headers", "HeaderPanel")
        values = ET.SubElement(headers, "collectionProp", name="HeaderManager.headers")
        header = ET.SubElement(values, "elementProp", name="", elementType="Header")
        prop(header, "Header.name", "Content-Type")
        prop(header, "Header.value", check.content_type)
        for name, value in check.headers.items():
            header = ET.SubElement(values, "elementProp", name="", elementType="Header")
            prop(header, "Header.name", name)
            prop(header, "Header.value", value)
        assertion, _ = node(children, "ResponseAssertion", "Expected HTTP status", "AssertionGui")
        patterns = ET.SubElement(assertion, "collectionProp", name="Asserion.test_strings")
        prop(patterns, "0", check.expected_status)
        prop(assertion, "Assertion.test_field", "Assertion.response_code")
        prop(assertion, "Assertion.test_type", 8, "intProp")
        prop(assertion, "Assertion.assume_success", "true", "boolProp")
        timing, _ = node(
            children, "DurationAssertion", "Response time budget", "DurationAssertionGui"
        )
        prop(timing, "DurationAssertion.duration", check.max_response_ms)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def database_script(request: ScriptPackRequest) -> str:
    statements = []
    for check in request.database_checks:
        case_id = check.case_id.replace("'", "''")
        count = f"SELECT COUNT(*) FROM (\n{check.query}\n) checked_rows"
        if request.target == "oracle":
            statements.append(
                "DECLARE\n  actual_rows NUMBER;\nBEGIN\n  "
                + count.replace("SELECT COUNT(*)", "SELECT COUNT(*) INTO actual_rows", 1)
                + f";\n  IF actual_rows <> {check.expected_rows} THEN\n"
                + f"    RAISE_APPLICATION_ERROR(-20001, '{case_id}: expected "
                + f"{check.expected_rows} rows, actual ' || actual_rows);\n  END IF;\n"
                + f"  DBMS_OUTPUT.PUT_LINE('{case_id}: PASS');\nEND;\n/"
            )
        else:
            statements.append(
                f"SELECT '{case_id}' AS case_id, {check.expected_rows} AS expected_rows,\n"
                + "  COUNT(*) AS actual_rows,\n"
                + f"  CASE WHEN COUNT(*) = {check.expected_rows} "
                + "THEN 'PASS' ELSE 'FAIL' END AS result\n"
                + f"FROM (\n{check.query}\n) checked_rows;"
            )
    preamble = "-- Generated checks: supplied SELECT queries and expected row counts.\n"
    if request.target == "oracle":
        preamble += (
            "WHENEVER OSERROR EXIT FAILURE ROLLBACK\n"
            "WHENEVER SQLERROR EXIT FAILURE ROLLBACK\nSET DEFINE OFF\nSET SERVEROUTPUT ON\n"
            "SPOOL TestResults/Reports/database-results.log\n"
        )
    suffix = "\nSPOOL OFF\nEXIT SUCCESS ROLLBACK\n" if request.target == "oracle" else "\n"
    return preamble + "\n\n".join(statements) + suffix


def build_pack(request: ScriptPackRequest) -> ScriptPack:
    require_implementation_approval(request.validation)
    checks = {
        "jmeter": request.http_checks,
        "browser": request.browser_checks,
        "sql": request.database_checks,
        "oracle": request.database_checks,
    }[request.target]
    if not checks:
        raise ValueError("Supply at least one case mapping for the selected script type.")
    if (
        sum(
            bool(group)
            for group in (request.http_checks, request.browser_checks, request.database_checks)
        )
        != 1
    ):
        raise ValueError("Supply only mappings for the selected script type.")
    if request.target == "browser" and (request.threads > 50 or request.duration_seconds):
        raise ValueError("Browser runs support at most 50 users and iteration-based workloads.")
    ids = [check.case_id for check in checks]
    suite_ids = [case.id for case in request.suite.test_cases]
    if (
        len(set(suite_ids)) != len(suite_ids)
        or len(set(ids)) != len(ids)
        or set(ids) != set(suite_ids)
    ):
        raise ValueError(
            "Supply exactly one mapping for every selected test case, with unique IDs."
        )
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", case_id) for case_id in ids):
        raise ValueError("Script case IDs must use letters, numbers, underscores or hyphens.")
    files = {
        "Input/CaseData.Json": request.suite.model_dump_json(indent=2),
        "Input/TestData.Json": json.dumps([check.model_dump() for check in checks], indent=2),
        "TestResults/Reports/README.md": "Execution output belongs here. No tests have been run.\n",
    }
    notes = ["Generated from explicit case mappings; target execution has not been performed."]
    readme = (
        "# " + request.target.upper() + " test pack\n\n"
        "Case coverage: " + ", ".join(ids) + ".\n\n"
        "Input/CaseData.Json retains selected cases; Input/TestData.Json retains mappings.\n"
        "Reqnroll contains runner configuration; Features contains the executable checks.\n"
        "StepDefinitions, Hooks, TestContext, Builders and Models are unused by these native "
        "script packs. Utilities contains measured reporting; browser Services contains "
        "journey execution. No BDD runtime or Playwright is required.\n\n"
    )
    if request.target == "jmeter":
        if quotation_feature(request.suite.feature_name):
            approved = json.loads(PAYLOAD_PATH.read_text(), parse_float=Decimal)
            for check in request.http_checks:
                if check.body and json.loads(check.body, parse_float=Decimal) != approved:
                    raise ValueError(
                        "Quotation request bodies must match the approved quotation payload."
                    )
        files["Features/performance.jmx"] = jmeter_plan(request)
        files["Reqnroll/jmeter.properties"] = (
            "# Set the target host before execution. Keep credentials outside the pack.\n"
            "host=\nprotocol=https\nport=\nconnect_timeout=10000\nresponse_timeout=30000\n"
            "jmeter.save.saveservice.output_format=csv\n"
            "jmeter.save.saveservice.timestamp_format=ms\n"
            "jmeter.save.saveservice.print_field_names=true\n"
            "jmeter.save.saveservice.assertion_results_failure_message=true\n"
            "jmeter.save.saveservice.response_data=false\n"
            "jmeter.save.saveservice.response_data.on_error=false\n"
            "jmeter.save.saveservice.time=true\n"
            "jmeter.save.saveservice.label=true\n"
            "jmeter.save.saveservice.successful=true\n"
            "jmeter.save.saveservice.latency=true\n"
            "jmeter.save.saveservice.connect_time=true\n"
            "jmeter.save.saveservice.thread_counts=true\n"
            "jmeter.save.saveservice.bytes=true\n"
            "jmeter.save.saveservice.sent_bytes=true\n"
            "jmeter.save.saveservice.response_code=true\n"
            "jmeter.save.saveservice.response_message=true\n"
        )
        for index, check in enumerate(request.http_checks, 1):
            if check.body:
                files[f"Input/body-{index:03d}.txt"] = check.body
        readme += (
            "## Run with Apache JMeter 5.6.3 or compatible\n\n"
            "Set host, protocol and port in Reqnroll/jmeter.properties. Run from the pack root:\n\n"
            "```sh\njmeter -n -t Features/performance.jmx -q Reqnroll/jmeter.properties "
            "-l TestResults/Reports/results.jtl -j TestResults/Reports/jmeter.log "
            "-e -o TestResults/Reports/html\n```\n\n"
            "Use a fresh JTL file and empty HTML output directory for each run. "
            "Review failed samples in the JTL and HTML report; JMeter process success alone "
            "does not mean assertions passed. The duration assertion is a per-response limit, "
            "not a percentile SLA. Each thread executes the supplied cases sequentially for "
            "the configured iteration count. Redirects are not followed. Add environment-specific "
            "authentication, correlation and pacing where the journey requires them.\n"
            "https://jmeter.apache.org/usermanual/get-started.html\n"
        )
    elif request.target == "browser":
        template = Path(__file__).parent / "templates/performance"
        files["Services/BrowserPerformanceService.py"] = (template / "browser.py").read_text()
        files["Features/browser-performance.py"] = (
            "import runpy\nfrom pathlib import Path\n"
            "runpy.run_path(str(Path(__file__).resolve().parents[1] / "
            "'Services/BrowserPerformanceService.py'), run_name='__main__')\n"
        )
        files["requirements.txt"] = "playwright>=1.49,<2\n"
        readme = readme.replace(
            "No BDD runtime or Playwright is required.",
            "Playwright Chromium is required; no BDD runtime is required.",
        )
        readme += (
            "## Real-browser performance (Python 3.11+)\n\n"
            "Install `python -m pip install -r requirements.txt` and "
            "`python -m playwright install chromium`. Set TARGET_BASE_URL to the actual origin "
            "and run `python Features/browser-performance.py`. "
            "Each isolated browser user runs the supplied actions and waits for your explicit "
            "ready selector. Optional BROWSER_STORAGE_STATE points to a private authenticated "
            "Playwright state file; action value_env reads secrets from runtime environment. "
            "Do not put credentials in Input. Journey timing includes navigation, actions and "
            "readiness. Samples include TTFB, DOMContentLoaded, load and available FCP timings. "
            "These are observed browser timings, not Lighthouse scores or field Core Web Vitals. "
            "Browser users share this load generator: monitor its CPU/memory. Maximum 50 users.\n"
        )
    else:
        files["Features/database.sql"] = database_script(request)
        files["Reqnroll/README.md"] = "Run Features/database.sql using your database client.\n"
        readme += (
            "## Database checks\n\n"
            "Each supplied SELECT returns the rows to count. Choose expected_rows=0 for "
            "queries that return violations (duplicates, missing relations or invalid values). "
            "Use queries written for your database and a read-only test account. Query shape "
            "checks do not validate schemas or prevent database function side effects.\n\n"
        )
        if request.target == "oracle":
            readme += (
                "Connect with SQL*Plus using a wallet or credentials outside this pack, "
                "then run `@Features/database.sql` from the pack root. PL/SQL raises on the first "
                "mismatch and SQL*Plus exits with failure. It rolls back on exit and records "
                "output in TestResults/Reports/database-results.log.\n"
            )
        else:
            readme += (
                "Execute Features/database.sql in your SQL client and export the result sets to "
                "TestResults/Reports. Each result includes case_id, expected_rows, actual_rows and "
                "PASS/FAIL. A FAIL is a failed test; client exit status alone does not enforce "
                "this. The wrapper uses standard SELECT/CASE; the supplied query must match your "
                "database dialect.\n"
            )
    if request.target in {"jmeter", "browser"}:
        template = Path(__file__).parent / "templates/performance"
        files["Utilities/PerformanceReportUtility.py"] = (template / "report.py").read_text()
        files["PERFORMANCE-PLAN.md"] = (template / "plan.md").read_text()
        files["Input/PerformanceConfig.Json"] = json.dumps(
            {
                "threads": request.threads,
                "ramp_seconds": request.ramp_seconds,
                "iterations": request.iterations,
                "duration_seconds": request.duration_seconds,
                "warmup_seconds": request.warmup_seconds,
                "think_time_ms": request.think_time_ms,
                "timeout_ms": request.timeout_ms,
                "checks": [{"case_id": check.case_id} for check in checks],
                "thresholds": {
                    "p95_ms": request.p95_ms,
                    "p99_ms": request.p99_ms,
                    "max_error_percent": request.max_error_percent,
                    "min_samples": request.min_samples,
                },
            },
            indent=2,
        )
        if request.target == "jmeter":
            files["Reqnroll/run.py"] = (template / "run.py").read_text()
            readme += (
                "\n## Recommended runner with CI gates (Python 3.11+)\n\n"
                "Set TARGET_BASE_URL; optionally JMETER_BIN and JMETER_PRIVATE_PROPERTIES "
                "for private authentication properties. Run `python Reqnroll/run.py`. "
                "The runner creates a unique timestamped results directory, JTL, JMeter "
                "dashboard and the shared measured report. Duration mode supersedes iterations.\n"
            )
        readme += (
            "\n## Workload, evidence and acceptance\n\n"
            "Input/PerformanceConfig.Json records workload and supplied budgets. No organisation "
            "SLA is inferred: p95/p99 gates are optional until supplied. The default error budget "
            "is zero and minimum samples is one; select business-approved budgets and adequate "
            "sample counts for your environment. Warm-up samples remain in raw data but are "
            "excluded from the shared summary. JMeter's dashboard includes all raw samples. "
            "Review per-case p50/p90/p95/p99, min/mean/max, throughput and error rate. "
            "Failures count in latency percentiles. Missing/insufficient samples fail the gate. "
            "The runner exits nonzero on tool, assertion or SLA failure. Reports include "
            "samples.json, summary.json, summary.csv and report.html.\n\n"
            "Use smoke, baseline, load, stress and soak runs with explicitly chosen load levels. "
            "Record deployment/version, environment, dataset, test window, generator capacity "
            "and server CPU/memory/DB/queue telemetry alongside the report. Correlate spikes "
            "with application traces. Repeat baselines under comparable conditions. "
            "Authentication setup, business data and API token/ID correlation must come from "
            "the actual contract; they are not fabricated by this generator.\n"
        )
    files["README.md"] = readme
    return ScriptPack(
        target=request.target,
        case_ids=ids,
        notes=notes,
        files=[ArtifactFile(path=path, content=content) for path, content in files.items()],
    )


@router.post("/generate", response_model=ScriptPack)
async def generate_scripts(request: ScriptPackRequest) -> ScriptPack:
    try:
        return build_pack(request)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/download")
async def download_scripts(request: ScriptPackRequest) -> Response:
    artifact = await generate_scripts(request)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in artifact.files:
            archive.writestr(file.path, file.content)
    return Response(
        output.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{request.target}-test-pack.zip"'},
    )
