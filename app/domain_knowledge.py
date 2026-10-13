"""Read BA reference topics from the same canonical HTML shown in the UK guide."""

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

from app.models import GenerateRequest

GUIDE_PATH = Path(__file__).parent / "static" / "auto-finance-uk.html"
GUIDE_TOPICS = (
    "overview",
    "products",
    "comparison",
    "brands",
    "journey",
    "costs",
    "protections",
    "glossary",
)
_VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_BLOCK = {"h2", "h3", "h4", "p", "li", "tr", "dt", "dd", "summary", "div"}


class GuideTopics(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current: str | None = None
        self.stack: list[tuple[str, bool]] = []
        self.parts: dict[str, list[str]] = {}
        self.references: dict[str, list[str]] = {}
        self.units: dict[str, list[dict]] = {}
        self.unit: tuple[str, int, int] | None = None
        self.unit_title = ""
        self.heading_start: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "section" and values.get("id") in GUIDE_TOPICS:
            self.current = values["id"]
            self.parts[self.current] = []
            self.references[self.current] = []
            self.units[self.current] = []
        ignored = (
            bool(self.stack and self.stack[-1][1])
            or tag in {"script", "style", "button", "select", "label", "nav", "aside"}
            or "toolbar" in (values.get("class") or "").split()
        )
        if tag not in _VOID:
            self.stack.append((tag, ignored))
        if self.current and not ignored:
            if self.unit is None and (
                tag == "article"
                or tag == "details"
                and self.current == "journey"
                or tag == "tr"
                and self.current == "brands"
            ):
                self.unit = (tag, len(self.parts[self.current]), len(self.references[self.current]))
                self.unit_title = ""
            if self.unit and tag in {"h3", "summary"}:
                self.heading_start = len(self.parts[self.current])
            if tag in _BLOCK or tag == "br":
                self.parts[self.current].append("\n")
            if tag == "a" and (values.get("href") or "").startswith("https://"):
                self.references[self.current].append(values["href"])
            if tag in {"td", "th"}:
                self.parts[self.current].append(" | ")

    def handle_endtag(self, tag: str) -> None:
        ignored = bool(self.stack and self.stack[-1][1])
        if self.current and self.unit and not ignored:
            if tag in {"h3", "summary"} and self.heading_start is not None:
                self.unit_title = " ".join(
                    "".join(self.parts[self.current][self.heading_start :]).split()
                )
                self.heading_start = None
            if tag == self.unit[0]:
                _, start, refs = self.unit
                content = "\n".join(
                    " ".join(line.split())
                    for line in "".join(self.parts[self.current][start:]).splitlines()
                    if line.strip()
                )
                self.units[self.current].append(
                    {
                        "title": self.unit_title or content.splitlines()[0],
                        "content": content,
                        "references": self.references[self.current][refs:],
                    }
                )
                self.unit = None
        if self.current and not ignored and tag in _BLOCK:
            self.parts[self.current].append("\n")
        if self.current and not ignored and tag in {"span", "td", "th"}:
            self.parts[self.current].append(" ")
        if self.current and tag == "section":
            self.current = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.current and not (self.stack and self.stack[-1][1]):
            self.parts[self.current].append(data)


def guide_knowledge_sources(*, include_units: bool = False) -> list[dict[str, str]]:
    html = GUIDE_PATH.read_text(encoding="utf-8")
    parser = GuideTopics()
    parser.feed(html)
    version = re.search(r"Public-source reference · v([\d.]+)", html)
    sources = []
    for topic in GUIDE_TOPICS:
        if topic not in parser.parts:
            raise ValueError(f"UK finance guide is missing topic: {topic}")
        lines = [" ".join(line.split()) for line in "".join(parser.parts[topic]).splitlines()]
        content = "\n".join(line for line in lines if line)
        if len(content) < 100:
            raise ValueError(f"UK finance guide topic is incomplete: {topic}")
        title = next((line for line in lines if line), topic)
        # The section's eyebrow precedes its actual heading.
        title = next((line for line in lines if line and not re.match(r"^\d+ /", line)), title)
        references = list(dict.fromkeys(parser.references[topic]))
        sources.append(
            {
                "id": f"UK-AUTO-FINANCE:{topic}",
                "version": version[1] if version else "unversioned",
                "title": "UK finance guide · " + title,
                "authority": "reference_only",
                "owner": "Public-source reference; business approval pending",
                "path": f"app/static/auto-finance-uk.html#{topic}",
                "reference_urls": "\n".join(references),
                "content": content
                + ("\nReference URLs:\n" + "\n".join(references) if references else ""),
                "fingerprint": hashlib.sha256(content.encode()).hexdigest(),
            }
        )
        if include_units:
            import json

            sources[-1]["units"] = json.dumps(parser.units[topic])
    return sources


_PRODUCTS = {
    "PCP": "Personal Contract Purchase",
    "HP": "Hire Purchase",
    "LP": "Lease Purchase",
    "PCH": "Personal Contract Hire",
    "BCH": "Business Contract Hire",
    "PFL": "Personal Finance Lease",
    "BFL": "Business Finance Lease",
}
_JOURNEYS = {
    "quotation": r"\b(?:quotes?|quotations?)\b",
    "application": r"\b(?:credit|finance|loan) application\b|\bKYC\b|identity verification",
    "underwriting": r"\bunderwriting\b|credit decision|affordability assessment",
    "agreement": r"contract signing|agreement activation|e-signature|contract finalis",
    "servicing": r"\bservicing\b|payment allocation|payment collection|direct debit",
    "arrears": r"\barrears\b|delinquen",
    "settlement": r"early settlement|finance closure|voluntary termination",
}
_JOURNEY_STEPS = {
    "quotation": {5},
    "application": {6},
    "underwriting": {7},
    "agreement": {8, 9, 10},
    "servicing": {11},
    "arrears": {11},
    "settlement": {11},
}


def scope_guide_sources(
    request: GenerateRequest, sources: list[dict[str, str]]
) -> tuple[list[dict[str, str]], dict[str, str | list[str]]]:
    """Select actual BRD scope; neighbouring lifecycle features do not become requirements."""
    import json

    clauses = re.split(r"[\n.!?]+", request.description)
    positive = " ".join(
        clause
        for clause in clauses
        if not re.search(
            r"out.of.scope|excluded?|not (?:in scope|required)|does not include", clause, re.I
        )
    )
    products = (
        [request.finance_product_id]
        if request.finance_product_id
        else [
            code
            for code, name in _PRODUCTS.items()
            if re.search(
                r"\b" + re.escape(code) + r"\b|\b" + re.escape(name) + r"\b", positive, re.I
            )
        ]
    )
    journeys = list(request.finance_journey_ids) or [
        name for name, pattern in _JOURNEYS.items() if re.search(pattern, positive, re.I)
    ]
    vehicle = (
        "new"
        if re.search(r"\bnew (?:vehicles?|cars?)\b", positive, re.I)
        else (
            "used"
            if re.search(r"\b(?:used|pre-owned) (?:vehicles?|cars?)\b", positive, re.I)
            else "unspecified"
        )
    )
    quotation = "quotation" in journeys
    trade_in = bool(
        re.search(
            r"part.exchange|trade.in|negative equity|old (?:finance|settlement)", positive, re.I
        )
    )
    selected = []
    for source in sources:
        topic = source["id"].split(":")[-1]
        units = json.loads(source.get("units", "[]"))
        chosen = []
        if topic == "products" and (products or quotation):
            chosen = [u for u in units if u["title"] in {_PRODUCTS.get(p) for p in products}]
            if not chosen:
                # Unknown product: supply the catalogue introduction, not every product's rules.
                chosen = [
                    {
                        "title": "Product context",
                        "content": source["content"].split("Hire Purchase", 1)[0],
                        "references": [],
                    }
                ]
        elif topic == "journey" and journeys:
            steps = set().union(*(_JOURNEY_STEPS.get(j, set()) for j in journeys))
            chosen = [
                u
                for u in units
                if re.match(r"^(\d+)", u["title"])
                and int(re.match(r"^(\d+)", u["title"])[1]) in steps
            ]
        elif topic == "costs" and (quotation or request.finance_calculation is not None):
            titles = (
                {"Lease reconciliation"}
                if set(products) <= {"PCH", "BCH", "PFL", "BFL"} and products
                else {"Purchase-finance reconciliation"}
            )
            chosen = [u for u in units if u["title"] in titles]
        elif topic == "brands":
            names = [
                name
                for name in (
                    "Volkswagen",
                    "Audi",
                    "Škoda",
                    "SEAT",
                    "CUPRA",
                    "BMW",
                    "MINI",
                    "Mercedes-Benz",
                    "Ford",
                    "Toyota",
                    "Lexus",
                    "Peugeot",
                )
                if re.search(r"\b" + re.escape(name) + r"\b", positive, re.I)
            ]
            chosen = [
                u
                for u in units
                if names and any(name.casefold() in u["content"].casefold() for name in names)
            ]
        elif topic == "protections":
            if "agreement" in journeys:
                chosen = [
                    u
                    for u in units
                    if u["title"]
                    in {
                        "Withdrawal is different from returning a car",
                        "Commission and Consumer Duty",
                    }
                ]
            if re.search(r"commission|Consumer Duty", positive, re.I):
                chosen.extend(
                    u
                    for u in units
                    if u["title"] == "Commission and Consumer Duty" and u not in chosen
                )
            if set(products) & {"BCH", "BFL"} and re.search(r"\bVAT\b|tax", positive, re.I):
                chosen.extend(u for u in units if u["title"] == "Business VAT, tax and accounting")
        if not chosen:
            continue
        texts = []
        for unit in chosen:
            text = unit["content"]
            if quotation and not trade_in:
                text = "\n".join(
                    sentence
                    for line in text.splitlines()
                    for sentence in re.split(r"(?<=[.!?])\s+", line)
                    if not re.search(
                        r"part.exchange|trade.in|negative equity|old (?:finance|settlement)",
                        sentence,
                        re.I,
                    )
                )
            texts.append(text)
        scoped = {key: value for key, value in source.items() if key != "units"}
        scoped["content"] = source["title"] + "\n" + "\n\n".join(texts)
        scoped["reference_urls"] = "\n".join(
            dict.fromkeys(url for u in chosen for url in u["references"])
        )
        scoped["selected_sections"] = "\n".join(u["title"] for u in chosen)
        scoped["fingerprint"] = hashlib.sha256(scoped["content"].encode()).hexdigest()
        selected.append(scoped)
    scope = {
        "product": ", ".join(products),
        "journeys": journeys,
        "vehicle_condition": vehicle,
        "scope_status": "identified" if journeys or products else "needs_clarification",
        "scope_basis": [
            "Explicit selectors take precedence; otherwise scope is detected from BRD wording."
        ],
        "included_topics": [s["title"] for s in selected],
        "excluded_topics": [
            s["title"] for s in sources if s["id"] not in {v["id"] for v in selected}
        ],
        "excluded_journeys": [name for name in _JOURNEYS if name not in journeys],
    }
    return selected, scope
