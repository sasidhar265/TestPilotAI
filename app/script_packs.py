"""Build traceable performance and database checks from explicit case inputs."""

import io
import json
import re
import zipfile
from decimal import Decimal
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


class ScriptPackRequest(StepDefinitionRequest):
    target: Literal["jmeter", "sql", "oracle"]
    http_checks: list[HttpCheck] = Field(default_factory=list, max_length=100)
    database_checks: list[DatabaseCheck] = Field(default_factory=list, max_length=100)
    threads: int = Field(default=1, ge=1, le=10000)
    ramp_seconds: int = Field(default=1, ge=1, le=86400)
    iterations: int = Field(default=1, ge=1, le=1000000)


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
    checks = request.http_checks if request.target == "jmeter" else request.database_checks
    if not checks:
        raise ValueError("Supply at least one case mapping for the selected script type.")
    if (request.target == "jmeter" and request.database_checks) or (
        request.target != "jmeter" and request.http_checks
    ):
        raise ValueError("Supply only mappings for the selected script type.")
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
        "StepDefinitions, Hooks, TestContext, Services, Builders, Models and Utilities are unused "
        "by these native script packs. No BDD runtime or Playwright is required.\n\n"
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
