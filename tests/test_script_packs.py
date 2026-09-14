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
