# Performance execution plan

## Scope and ownership
Use Input/CaseData.Json as the selected requirements and Input/TestData.Json as the exact
executable mapping. Confirm that every mapping represents the intended business journey.
Record the business owner, performance engineer and environment owner with the run evidence.
Business rules, request bodies and UI selectors must be supplied and approved, never inferred.

## Workload model
Input/PerformanceConfig.Json defines the chosen users, ramp, repetitions, pacing, warm-up
and acceptance budgets. This is a closed-user model: slower journeys reduce throughput.
It does not guarantee a fixed arrival rate. Requests/cases run in sequence per user.
For a production-like journey, select the actual operations and data in their required order.
Record forecast peak users/transactions, observed journey mix, dataset size and cache behavior.

Choose load deliberately for each run:
- Smoke: verify transport, authentication, readiness and assertion accuracy at minimal load.
- Baseline: repeat a stable representative workload on a known release.
- Load: use the business-approved expected peak workload and measurement window.
- Stress: increment load in separate runs to locate degradation and recovery boundaries.
- Soak: use a sustained duration/iteration count and monitor memory, pools and queues.

No example concurrency or SLA should be treated as an approved capacity target.
Browser virtual users share a Chromium process and machine; record CPU/memory and calibrate
its capacity. Browser measurements describe user journeys; use JMeter for high-volume API load.

## Environment and inputs
Record deployment/build SHA, environment, topology, region, browser/tool/Python versions,
test window, dataset version, connection limits and dependent-service configuration.
Use TARGET_BASE_URL; runtime authentication comes from private JMeter properties or browser
storage state. Keep secrets outside Input files and source control. Explicit fill actions
can reference value_env. Verify token expiry, data collision behavior and correlation needs
against the actual API contract before increasing load. Approved quotation fields stay intact.
Provide correlation/data variation explicitly; this pack does not infer either.

## Execution and operational controls
Verify readiness with a smoke run. Ensure the measurement window extends beyond warm-up.
Use fresh timestamped reports. Monitor generator CPU/memory and server CPU, memory, GC,
connection/thread pools, database latency/locks, dependent services and queue depth.
Agree stop criteria with the environment owner before stress or soak testing. Preserve failed
samples and failed runs. Do not rerun a failed sample until it passes to disguise reliability.

## Results and acceptance
Open TestResults/Reports/<run-id>/report.html and retain its raw samples and summary JSON/CSV.
Inspect per-case count, error rate, p50/p90/p95/p99, mean/min/max and observed throughput.
Percentiles include failures and use nearest rank. At small sample counts p99 can equal the
maximum; do not interpret a smoke run as a statistically reliable percentile estimate.
Warm-up is excluded from the shared summary, but remains in raw results/JMeter's dashboard.
Check the minimum measured samples gate and every supplied budget. Runner exit status fails
on infrastructure, assertion or budget failure. A successful JMeter process is insufficient.
Browser samples contain action timings, navigation metrics and browser/network failure counts.
Browser navigation timings are measured in the current page, not field Core Web Vitals.

## Analysis and release recommendation
Compare with a baseline under equivalent conditions. Explain regressions and correlate spikes
with server traces/telemetry. Identify the saturated resource and demonstrate recovery before
claiming capacity. Record a recommendation, outstanding constraints and owner approval.
Keep functional correctness, commercial suitability and release approval separate from timings.
