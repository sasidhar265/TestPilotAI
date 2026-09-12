"""The user-approved quotation request, shared by every language generator."""

import re
from pathlib import Path

PAYLOAD_PATH = Path(__file__).parent / "templates" / "framework" / "QuotationRequest.Json"


def quotation_feature(name: str) -> bool:
    return bool(
        re.search(r"\b(?:quotation|quotations|quote|quotes|finance|financing)\b", name, re.I)
    )


def quotation_sources() -> dict[str, str]:
    templates = Path(__file__).parent / "templates" / "reqnroll"
    return {
        path: (templates / Path(path).name).read_text()
        for path in (
            "Models/QuotationRequestModel.cs",
            "Builders/QuotationRequestbuilder.cs",
            "Services/QuotationRequestService.cs",
        )
    }


def quotation_instructions() -> str:
    from app.agent_instructions import load_agent_instructions

    return load_agent_instructions("test-data").replace(
        "{approved_payload}", PAYLOAD_PATH.read_text()
    )
