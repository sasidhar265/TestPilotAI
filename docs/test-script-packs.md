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

`automation/Features/ScriptPacks.feature` exercises all three generation and download targets
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
