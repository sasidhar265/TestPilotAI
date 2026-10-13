"""Aggregate observed samples; thresholds come from the approved run configuration."""

import csv
import html
import json
import math
from pathlib import Path


def percentile(values, percent):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percent / 100) - 1)]


def report(samples, config, output, metadata):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "samples.json").write_text(json.dumps(samples, indent=2))
    measured = [s for s in samples if not s.get("warmup", False)]
    grouped = {check["case_id"]: [] for check in config["checks"]}
    for sample in measured:
        grouped.setdefault(sample["case_id"], []).append(sample)
    rows = []
    for case_id, group in grouped.items():
        values = [s["elapsed_ms"] for s in group]
        errors = sum(not s["success"] for s in group)
        seconds = (
            ((max(s["end_ms"] for s in group) - min(s["start_ms"] for s in group)) / 1000)
            if group
            else 0
        )
        row = {
            "case_id": case_id,
            "samples": len(group),
            "errors": errors,
            "error_percent": round(100 * errors / len(group), 3) if group else None,
            "throughput_per_second": round(len(group) / seconds, 3) if seconds > 0 else None,
            "min_ms": round(min(values), 2) if values else None,
            "mean_ms": round(sum(values) / len(values), 2) if values else None,
            "max_ms": round(max(values), 2) if values else None,
        }
        row.update(
            {
                f"p{p}_ms": round(percentile(values, p), 2) if values else None
                for p in (50, 90, 95, 99)
            }
        )
        reasons = []
        thresholds = config["thresholds"]
        if len(group) < thresholds["min_samples"]:
            reasons.append("Insufficient measured samples")
        if errors / max(1, len(group)) * 100 > thresholds["max_error_percent"]:
            reasons.append("Error-rate budget exceeded")
        for metric in ("p95_ms", "p99_ms"):
            budget = thresholds.get(metric)
            if budget is not None and values and row[metric] > budget:
                reasons.append(metric + " budget exceeded")
        row["passed"] = not reasons
        row["reasons"] = reasons
        rows.append(row)
    passed = bool(rows) and all(r["passed"] for r in rows)
    result = {
        "passed": passed,
        "metadata": metadata,
        "configuration": config,
        "warmup_samples_excluded": len(samples) - len(measured),
        "cases": rows,
        "method": (
            "Nearest-rank percentiles over measured samples, including failures; "
            "per-case throughput uses observed wall time."
        ),
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    columns = [key for key in rows[0] if key != "reasons"] if rows else ["case_id"]
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    def escape(value):
        return html.escape(str(value))

    head = "".join("<th>" + escape(c) + "</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join("<td>" + escape(r[c]) + "</td>" for c in columns) + "</tr>" for r in rows
    )
    issues = "".join(
        "<li>" + escape(r["case_id"] + ": " + ", ".join(r["reasons"])) + "</li>"
        for r in rows
        if r["reasons"]
    )
    document = f"""<!doctype html>
    <html lang="en">
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Performance execution report</title>
    <style>body{{font:14px/1.6 system-ui;background:#f4f7fa;color:#203247;margin:24px}}
    main{{padding:28px;background:white;border-radius:14px}}
    table{{border-collapse:collapse;width:100%}}
    td,th{{padding:10px;border-bottom:1px solid #dde5ef;text-align:left}}
    .scroll{{overflow:auto}}
    pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
    @media print{{body{{margin:0}}}}</style>
    <main>
    <h1>Performance execution report · {"PASS" if passed else "FAIL"}</h1>
    <p>{escape(metadata)}</p>
    <p>{escape(result["method"])}</p>
    <p>Warm-up samples excluded: {result["warmup_samples_excluded"]}.</p>
    <div class="scroll">
    <table>
    <thead>
    <tr>{head}</tr>
    </thead>
    <tbody>{body}</tbody>
    </table>
    </div>
    <ul>{issues}</ul>
    <h2>Workload and supplied budgets</h2>
    <pre>{escape(json.dumps(config, indent=2))}</pre>
    <p>Measured results from this run only. Review sample counts,
    load-generator capacity and server telemetry
    before capacity or production decisions.</p>
    </main>
    </html>"""
    (output / "report.html").write_text(document)
    return passed


def jtl_samples(path, warmup_seconds):
    with Path(path).open() as stream:
        rows = list(csv.DictReader(stream))
    first = min((float(row["timeStamp"]) for row in rows), default=0)
    return [
        {
            "case_id": r["label"],
            "start_ms": float(r["timeStamp"]),
            "end_ms": float(r["timeStamp"]) + float(r["elapsed"]),
            "elapsed_ms": float(r["elapsed"]),
            "success": r["success"].lower() == "true",
            "status": r.get("responseCode"),
            "bytes": r.get("bytes"),
            "latency_ms": r.get("Latency"),
            "connect_ms": r.get("Connect"),
            "active_threads": r.get("allThreads"),
            "warmup": float(r["timeStamp"]) < first + warmup_seconds * 1000,
        }
        for r in rows
    ]
