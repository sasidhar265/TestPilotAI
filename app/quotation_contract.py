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
    return (
        "\nAUTHORITATIVE QUOTATION REQUEST CONTRACT (user supplied; takes precedence over "
        "older BRD request examples and cached code):\n"
        + PAYLOAD_PATH.read_text()
        + "\nFor quotation/finance endpoints build only this wire shape with a typed fluent "
        "QuotationRequestBuilder. Preserve all field names and capitalization, including "
        "Outlet.code and Vehicle.VehicleRegstrationDate. Keep money/rates decimal and dates "
        "as the supplied date-only string. Read the supplied defaults from "
        "Input/QuotationRequest.Json. Only override known fields using explicitly approved "
        "Examples/test data. Never add customerType, eligibility, brand, maintenance, "
        "oracle or version metadata to the request body. They may be separate test context "
        "only if needed by the approved scenarios. These sample values are not evidence of "
        "catalogue validity or a successful response. Do not invent endpoint paths or methods. "
        "Keep endpoint/method/authentication in runtime configuration. Do not change unrelated "
        "application endpoints to accept this finance payload.\n"
        "Step definitions delegate to builders/services/strategies: no if, else, switch, "
        "match, case, unless or ternary conditional expressions in step-definition code. "
        "Use small injected strategies for behavior that actually varies; do not move a "
        "large conditional dispatcher into another class. Keep validation and assertions "
        "explicit in their appropriate services.\n"
    )
