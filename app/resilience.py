"""Local operator commands for recovery evidence and DORA gap tracking."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from app.audit_integrity import verify_audit
from app.recovery import backup_database, restore_database, write_private_json


def readiness_report(database: Path, checkpoint: Path | None = None) -> dict[str, Any]:
    """Report observed audit integrity without asserting regulatory compliance."""
    trusted = json.loads(checkpoint.read_text()) if checkpoint else None
    if checkpoint is not None and not isinstance(trusted, dict):
        raise ValueError("Invalid audit checkpoint")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        audit = verify_audit(db, trusted)
    return {
        "compliance_status": "not-established",
        "scope": "Local lifecycle audit only; deployment and organizational controls unverified.",
        "audit": audit,
        "independent_checkpoint_supplied": checkpoint is not None,
        "open_requirements": [
            "Determine regulated entity, applicable scope and accountable management owners.",
            "Approve ICT asset/dependency inventory, risk assessment and security controls.",
            "Verify production identity, least privilege, encryption, monitoring and alerts.",
            "Protect audit checkpoints independently; enforce retention and review access.",
            "Exercise full recovery, approve RTO/RPO and protect off-site backups.",
            "Approve incident classification, escalation, reporting and communication procedures.",
            "Execute resilience/security tests, record findings and verify remediation.",
            "Review supplier contracts, register of information, concentration and exit plans.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "restore"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path)
        command.add_argument("destination", type=Path)
    audit = commands.add_parser("audit")
    audit.add_argument("database", type=Path)
    audit.add_argument("--checkpoint", type=Path)
    audit.add_argument("--export-checkpoint", type=Path)
    readiness = commands.add_parser("readiness")
    readiness.add_argument("database", type=Path)
    readiness.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            result = backup_database(args.source, args.destination)
        elif args.command == "restore":
            result = restore_database(args.source, args.destination)
        else:
            result = readiness_report(args.database, args.checkpoint)
            if args.command == "audit":
                result = result["audit"]
                if args.export_checkpoint:
                    write_private_json(args.export_checkpoint, result)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(
            1,
            f"Resilience verification failed ({type(exc).__name__}). "
            "Check source integrity, format and destination permissions.\n",
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
