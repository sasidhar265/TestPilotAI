# Performance and database test scripts

Generate and validate a suite, select the cases to include, and choose **Test scripts** in
the generated-suite toolbar. Both manual and automation cases can be used. Choose a script
type, complete the case mappings, select **Generate scripts**, then review individual files
or download the ZIP. Editing a mapping invalidates the previous preview.

## Apache JMeter

For each case, supply its HTTP method, relative path, expected response status and maximum
response time. Supply the approved body for requests that need one. Workload settings specify
concurrent users, ramp-up seconds and iterations per user; defaults are one user and one
iteration. Optional headers support JMeter property references such as `${__P(api_token,)}`;
keep the corresponding property values in your environment's private configuration.

The pack contains `Features/performance.jmx`, runner properties, exact body files, and the
selected case/input records. Configure the actual host in `Reqnroll/jmeter.properties`, then
run the command in the pack's README from its root. It writes JTL results and an HTML report
under `TestResults/Reports`. Use fresh result files for every run.

The plan executes the selected requests sequentially per user, with a status assertion and
per-response duration assertion on every request. The duration limit is not a percentile SLA.
Authentication flows, correlation, pacing, and environment-specific test data need to be
configured for the target journey. JMeter process exit success does not imply assertion
success: inspect JTL success flags and the HTML report. See the official
[JMeter CLI documentation](https://jmeter.apache.org/usermanual/get-started.html) and
[assertion reference](https://jmeter.apache.org/usermanual/component_reference.html).

Quotation request bodies must match the shared approved quotation payload. The builder does
not infer finance fields or endpoint contracts. Request bodies are stored as exact text files,
preserving decimal text and preventing body strings from being interpreted as JMeter functions.

## SQL and Oracle SQL

Supply a single SELECT query and the expected number of rows for each case. A query returning
invalid records with an expected count of zero can check duplicates, orphaned rows, missing
values or other supplied business conditions. The generator wraps your query; it does not
invent tables, joins, columns or expected values. Queries must be written for your database.
Comments, internal semicolons, SELECT INTO and FOR UPDATE are unsupported.

- **SQL** emits SELECT/CASE result sets containing case ID, expected rows, actual rows and
  PASS/FAIL. The client or CI integration must treat any FAIL as a failing test. This wrapper
  has been exercised on SQLite; your database dialect still needs target execution.
- **Oracle** emits PL/SQL assertions and a SQL\*Plus script with spool output. A row-count
  mismatch raises an application error and exits with failure. The script stops at the first
  failure and rolls back on exit. Connect using your environment's credentials or wallet.

Use a read-only test account. Query shape validation is not a database security sandbox;
functions inside SELECT statements can have side effects. No database connection or SQL
execution is performed by the application when generating or downloading scripts.

## Traceability and layout

Every selected case must have exactly one mapping. Unknown, missing and duplicate IDs are
rejected. `Input/CaseData.Json` contains the cases, and `Input/TestData.Json` contains explicit
mappings. These native script packs use the shared `Features`, `Reqnroll`, `Input` and
`TestResults/Reports` folders. Their READMEs document the unused framework roles; native
JMeter/SQL checks do not require BDD bindings or Playwright.

The fields `method`, `path`, `request_body`, `content_type`, `expected_status`,
`max_response_ms`, `query`, and `expected_rows` in case test data prefill matching controls.
Always review these values before generation. The API exposes `POST /api/script-packs/generate`
for preview and `POST /api/script-packs/download` for a ZIP, using the same validated request.

## Reporting

**Progress & execution** includes an executive summary, latest pass-rate change, outcome
distribution, selectable run trends, test-level evidence and searchable run history.
**Export history · CSV** exports only rows matching the current search/status filters.
Missing results remain unavailable; pass rates exclude tests not run. Current-suite design
coverage remains separate from measured execution. Native script reports are created by their
target tools and are not imported into the repository BDD dashboard.

## Verification

`automation/Features/ScriptPacks.feature` exercises API performance, browser performance and database generation/download targets
plus mapping and approval failures through ReqnRoll and HttpClient. Its fixtures use the
existing workspace health endpoint and constant SQL queries; they do not invent business
schemas. Run against a separately started test application:

```sh
QUALITY_LIFECYCLE_BASE_URL=http://127.0.0.1:8766 \
dotnet test automation/QualityLifecycle.Automation.csproj \
  --filter 'FullyQualifiedName~PerformanceAndDatabaseScriptPacks' \
  --results-directory automation/TestResults/Reports/script-packs
```

Supply `API_AUTH_TOKEN` when the target requires authentication. Repository API tests verify
the script-building boundary. Execute each resulting native pack in its actual environment
to verify its behavior; API test success does not establish load-test or database correctness.

## Detailed performance packs

The builder now offers **API performance · Apache JMeter** and **UI performance ·
Playwright Chromium**. Both retain the approved case mappings and use the shared framework
layout. Performance workload and acceptance budgets include users, ramp-up, iterations,
pacing, excluded warm-up time, p95/p99 limits, maximum error rate and minimum measured samples.
API duration mode overrides iterations. No percentile SLA is invented: supply the budgets
approved for your environment. A one-sample default is for a smoke run, not a capacity study.

API packs include a per-user CookieManager, request status/duration assertions, optional
pacing, exact approved payload files, properties and `Reqnroll/run.py`. With JMeter installed,
set `TARGET_BASE_URL` and run `python Reqnroll/run.py`. `JMETER_BIN` selects the executable;
`JMETER_PRIVATE_PROPERTIES` points to private authentication properties. Browser packs require
Playwright Chromium, explicit relative page paths, readiness selectors and optional JSON
journey actions. Supported actions are `click`, `fill`, `select` and `wait_visible`, each
with a selector; fill/select use `value`, and secret fill values use `value_env` instead.
Set `TARGET_BASE_URL`, optionally private `BROWSER_STORAGE_STATE`, and run
`python Features/browser-performance.py`. Browser concurrency is limited to 50 users.

Runners produce unique directories under `TestResults/Reports`, retaining `samples.json`,
`summary.json`, `summary.csv` and a standalone `report.html`. API runs also retain JTL,
JMeter logs and the native dashboard. Reports show sample counts, errors, error percentage,
throughput, min/mean/max and nearest-rank p50/p90/p95/p99. Browser samples include individual
action durations, navigation TTFB/DOMContentLoaded/load and available FCP timings. Browser
HTTP/network/page errors and journey-budget failures count as failed samples. These browser
measurements are not field Core Web Vitals or Lighthouse scores.

Warm-up remains in raw evidence but is excluded from the shared aggregate/gates; JMeter's
native dashboard includes raw warm-up samples. Failed samples remain in percentile calculations.
Absent or insufficient measured samples fail. Tool/infrastructure and budget failures return a
nonzero runner exit code. These native results are not automatically imported into the BDD
execution dashboard. Keep the run environment, deployment, dataset, load-generator capacity
and server/DB/queue telemetry with the report before interpreting capacity or bottlenecks.
Authentication sequences, correlation and data variation must follow the target contract;
no login flow, business endpoint, selector or lender rule is inferred.
