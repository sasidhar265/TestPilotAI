"""Create a source-preserving BRD revision from explicit human finding decisions."""

from app.services.sdlc import SDLCError


def revised_document(document: str, run: dict) -> tuple[str, dict]:
    findings = run["output"]["findings"]
    if any(item["review_status"] == "PENDING" for item in findings):
        raise SDLCError("Record a decision on every suggestion before updating the BRD")
    replacements, amendments, pending, applied, declined = [], [], [], [], []
    for finding in findings:
        status = finding["review_status"]
        events = [
            event for event in run["decisions"] if event["finding_id"] == finding["finding_id"]
        ]
        effective = next(
            (
                event["action"]
                for event in reversed(events)
                if event["action"] not in {"comment", "resolve"}
            ),
            None,
        )
        if status == "REJECTED":
            declined.append(finding["finding_id"])
            continue
        if status == "CLARIFICATION_REQUESTED":
            pending.append(
                dict(
                    finding_id=finding["finding_id"],
                    question=finding["clarification_question"],
                    comment=events[-1]["comment"] if events else "",
                )
            )
            continue
        if status not in {"ACCEPTED_DRAFT", "EDITED_DRAFT"} and effective not in {"accept", "edit"}:
            continue
        wording = finding.get("human_proposed_text") or finding.get("suggested_requirement_text")
        if not wording or not wording.strip():
            raise SDLCError("Accepted suggestions need proposed wording. Edit the suggestion first")
        references = [ref for ref in finding["evidence_references"] if ref["source_id"] == "BRD"]
        quotes = list(dict.fromkeys(ref["quote"] for ref in references))
        # Replace only a single unambiguous, non-overlapping source quote. Otherwise retain
        # the source and attach an explicit superseding amendment rather than guessing a span.
        span = None
        if len(quotes) == 1 and document.count(quotes[0]) == 1:
            start = document.index(quotes[0])
            candidate = (start, start + len(quotes[0]), wording.strip())
            if not any(candidate[0] < old[1] and old[0] < candidate[1] for old in replacements):
                span = candidate
        if span:
            replacements.append(span)
        else:
            locations = ", ".join(ref.get("section_id") or "BRD" for ref in references)
            amendments.append(
                f"### {finding['title']}\nApplies to: {locations or 'linked BRD requirements'}. "
                "This BA-accepted amendment supersedes differing wording in the linked source.\n\n"
                + wording.strip()
            )
        applied.append(finding["finding_id"])
    text = document
    for start, end, wording in sorted(replacements, reverse=True):
        text = text[:start] + wording + text[end:]
    if amendments:
        text += "\n\n## BA-accepted amendments\n\n" + "\n\n".join(amendments)
    if pending:
        text += "\n\n## Open BA change requests — not approved business rules\n\n"
        text += "\n\n".join(
            f"- {item['question']}\n  BA feedback: {item['comment']}" for item in pending
        )
    if len(text) > 30000:
        raise SDLCError(
            "Updated BRD exceeds 30,000 characters. Consolidate the document in Requirements"
        )
    return text, dict(
        from_review=run["id"],
        review_revision=run["revision"],
        from_baseline=run["baseline"],
        applied_findings=applied,
        declined_findings=declined,
        pending_feedback=pending,
    )
