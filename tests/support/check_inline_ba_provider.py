"""Opt-in real provider check using a synthetic BRD, never customer information."""

import asyncio
import json

from app.agents.inline_business_analyst import InlineBusinessAnalyst, source_sections
from app.config import Settings
from app.models import GenerateRequest


async def main():
    request = GenerateRequest(
        description=(
            "PCP quotation BRD. The consumer quotation API must display a monthly payment, "
            "deposit, agreement term and optional final payment based on GMFV. The GMFV "
            "data source, missing-value handling, approved repayment formula and rounding "
            "method are not specified. This BRD covers quotation only; underwriting and "
            "contract signing are excluded."
        ),
        llm_model="codex",
    )
    agent = InlineBusinessAnalyst(Settings(_env_file=None, codex_artifact_timeout_seconds=300))
    sources, _, limitations, _ = agent.review_knowledge(request)
    output = await agent.analyse(
        request, source_sections(request.description), sources, limitations
    )
    assert any(
        finding["finding_type"] in {"CALCULATION_GAP", "INTEGRATION_DEPENDENCY"}
        for finding in output["findings"]
    )
    assert output["readiness_status"] == "BLOCKED"
    print(
        json.dumps(
            dict(
                status="LIVE_PROVIDER_PASSED",
                provider="codex",
                model="gpt-6-astra",
                readiness=output["readiness_status"],
                finding_types=[f["finding_type"] for f in output["findings"]],
            )
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
