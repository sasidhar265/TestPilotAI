"""Verify native script semantics, input fidelity and complete case coverage."""

import json
import os
import sqlite3
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from app.script_packs import ScriptPackRequest, build_pack


def request_for(target):
    return json.loads(Path("automation/Input/ScriptPacks.Json").read_text())[target]


def files_for(data):
    return {
        file.path: file.content for file in build_pack(ScriptPackRequest.model_validate(data)).files
    }


@pytest.mark.parametrize("expected,result", [(1, "PASS"), (0, "FAIL")])
def test_sql_executes_and_detects_wrong_row_count(expected, result):
    data = request_for("sql")
    data["database_checks"][0]["expected_rows"] = expected
    script = files_for(data)["Features/database.sql"]
    with sqlite3.connect(":memory:") as connection:
        row = connection.execute(script).fetchone()
    assert row == ("TC-SQL-001", expected, 1, result)


def test_jmeter_preserves_payload_and_assertions():
    data = request_for("jmeter")
    payload = '{"value":"${literal} & <test>","amount":1234567890.123456789}'
    data["http_checks"][0].update(method="POST", body=payload, expected_status=409)
    files = files_for(data)
    root = ET.fromstring(files["Features/performance.jmx"])
    assert root.find(".//HTTPSamplerProxy").get("testname") == "TC-HEALTH-001"
    assert root.find(".//ResponseAssertion/collectionProp/stringProp").text == "409"
    assert root.find(".//DurationAssertion/stringProp").text == "5000"
    assert files["Input/body-001.txt"] == payload
    assert "${literal}" not in files["Features/performance.jmx"]
    assert root.find(".//stringProp[@name='Argument.value']").text.startswith("${__FileToString(")


def test_oracle_has_failed_assertion_exit_and_exact_query():
    data = request_for("oracle")
    script = files_for(data)["Features/database.sql"]
    assert data["database_checks"][0]["query"] in script
    assert "WHENEVER SQLERROR EXIT FAILURE ROLLBACK" in script
    assert "RAISE_APPLICATION_ERROR(-20001" in script
    assert "IF actual_rows <> 1 THEN" in script
    assert "SET DEFINE OFF" in script


@pytest.mark.parametrize(
    "fixture", ["missing", "unknown-case", "duplicate-case", "failed-gate", "invalid-query"]
)
def test_invalid_mappings_fail(fixture):
    with pytest.raises(ValueError):
        files_for(request_for(fixture))


def test_quotation_rejects_invented_payload():
    data = request_for("jmeter")
    data["suite"]["feature_name"] = "Quotation API"
    data["http_checks"][0].update(method="POST", body='{"invented":true}')
    with pytest.raises(ValueError, match="approved quotation"):
        files_for(data)


@pytest.mark.skipif(not os.environ.get("JMETER_BIN"), reason="Set JMETER_BIN for native execution")
def test_jmeter_runtime_payload_status_and_duration(tmp_path):
    import copy
    import csv
    import subprocess
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    payload = '{"value":"${literal} & <test>","amount":1234567890.123456789}'
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.rfile.read(int(self.headers["Content-Length"])).decode())
            if self.path == "/slow":
                time.sleep(0.1)
            self.send_response(201)
            self.end_headers()
            self.wfile.write(b"created")

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        data = request_for("jmeter")
        template = data["suite"]["test_cases"][0]
        data["suite"]["test_cases"] = []
        data["http_checks"] = []
        for identifier, path, status, duration in [
            ("TC-PASS", "/echo", 201, 5000),
            ("TC-STATUS", "/echo", 200, 5000),
            ("TC-DURATION", "/slow", 201, 1),
        ]:
            case = copy.deepcopy(template)
            case["id"] = identifier
            data["suite"]["test_cases"].append(case)
            data["http_checks"].append(
                dict(
                    case_id=identifier,
                    path=path,
                    method="POST",
                    body=payload,
                    expected_status=status,
                    max_response_ms=duration,
                )
            )
        for path, content in files_for(data).items():
            file = tmp_path / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)
        result = subprocess.run(
            [
                os.environ["JMETER_BIN"],
                "-n",
                "-t",
                "Features/performance.jmx",
                "-Jhost=127.0.0.1",
                f"-Jport={server.server_port}",
                "-Jprotocol=http",
                "-l",
                "TestResults/Reports/runtime.jtl",
                "-j",
                "TestResults/Reports/runtime.log",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        with (tmp_path / "TestResults/Reports/runtime.jtl").open() as stream:
            rows = list(csv.DictReader(stream))
        assert [(row["label"], row["success"]) for row in rows] == [
            ("TC-PASS", "true"),
            ("TC-STATUS", "false"),
            ("TC-DURATION", "false"),
        ]
        assert received == [payload] * 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_performance_packs_have_workload_runner_and_measured_reporting():
    for name in ("performance-api", "browser"):
        files = files_for(request_for(name))
        config = json.loads(files["Input/PerformanceConfig.Json"])
        assert config["thresholds"]["min_samples"] >= 2
        assert "Utilities/PerformanceReportUtility.py" in files
        assert "summary.csv" in files["Utilities/PerformanceReportUtility.py"]
        assert "report.html" in files["Utilities/PerformanceReportUtility.py"]
        assert "No tests have been run" in files["TestResults/Reports/README.md"]
    root = ET.fromstring(files_for(request_for("performance-api"))["Features/performance.jmx"])
    assert root.find(".//CookieManager") is not None
    assert root.find(".//ConstantTimer") is not None
    assert root.find(".//boolProp[@name='Assertion.assume_success']").text == "true"


def test_measured_report_fails_percentile_errors_and_missing_samples(tmp_path):
    from app.templates.performance.report import report

    config = {
        "checks": [{"case_id": "C1"}, {"case_id": "C2"}],
        "thresholds": {"p95_ms": 50, "p99_ms": None, "max_error_percent": 0, "min_samples": 2},
    }
    samples = [
        dict(case_id="C1", elapsed_ms=100, start_ms=1000, end_ms=1100, success=True),
        dict(case_id="C1", elapsed_ms=10, start_ms=1100, end_ms=1110, success=False),
        dict(case_id="C1", elapsed_ms=9999, start_ms=0, end_ms=9999, success=True, warmup=True),
    ]
    assert not report(samples, config, tmp_path, {"run": "fixture"})
    result = json.loads((tmp_path / "summary.json").read_text())
    assert result["warmup_samples_excluded"] == 1
    assert result["cases"][0]["p95_ms"] == 100
    assert result["cases"][0]["error_percent"] == 50
    assert result["cases"][1]["reasons"] == ["Insufficient measured samples"]


def test_browser_requires_explicit_readiness_and_bounded_load():
    with pytest.raises(ValueError):
        files_for(request_for("missing-browser-selector"))
    data = request_for("browser")
    data["threads"] = 51
    with pytest.raises(ValueError, match="at most 50"):
        files_for(data)
