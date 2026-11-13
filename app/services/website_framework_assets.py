"""Create named page objects and independently discoverable BDD suites from evidence."""

import json
import re
from urllib.parse import urlsplit

from app.services.website_inspection import WebsiteInspection

SUITES = {
    "smoke": ("Smoke website readiness", "Smoke"),
    "sanity": ("Sanity website navigation", "Sanity"),
    "regression": ("Regression website contracts", "Regression"),
}


def identifier(text: str, fallback: str) -> str:
    value = "".join(word[:1].upper() + word[1:] for word in re.findall(r"[A-Za-z0-9]+", text))
    return (value if value and not value[0].isdigit() else fallback + value)[:70] or fallback


def safe_name(text: str) -> str:
    return " ".join(text.split())[:180]


def page_assets(inspection: WebsiteInspection) -> tuple[dict[str, str], list[dict[str, str]]]:
    files: dict[str, str] = {}
    cases: list[dict[str, str]] = []
    pages = []
    names: set[str] = {"basepage"}
    counters = dict.fromkeys(SUITES, 0)
    targets = {page.url: page for page in inspection.pages}
    registry = []

    def add(
        category: str, page_id: str, kind: str, expected: str, title: str, **extra: str
    ) -> None:
        counters[category] += 1
        cases.append(
            {
                "id": f"{category.upper()}-{counters[category]:03d}",
                "category": category,
                "pageId": page_id,
                "kind": kind,
                "expected": expected,
                "title": safe_name(title),
                **extra,
            }
        )

    for number, page in enumerate(inspection.pages, 1):
        path = urlsplit(page.url).path or "/"
        name = identifier(path.strip("/") or "Home", "Site") + "Page"
        if name.casefold() in names:
            name = name.removesuffix("Page") + str(number) + "Page"
        names.add(name.casefold())
        page_id = f"page-{number:03d}"
        pages.append({"pageId": page_id, "className": name, "url": page.url})
        registry.append(f"            [{json.dumps(page_id)}] = () => new {name}(driver, settings)")
        locators, members, methods, keys = [], [], [], set()
        for index, control in enumerate(page.controls, 1):
            selector = control.get("selector")
            if not selector:
                continue
            label = (
                control.get("aria-label")
                or control.get("id")
                or control.get("name")
                or f"Control {index}"
            )
            key = identifier(label, "Control") + identifier(
                control.get("tag", "Element"), "Element"
            )
            if key in keys:
                key += str(index)
            keys.add(key)
            members.append(
                f"    [FindsBy(How = How.CssSelector, Using = {json.dumps(selector)})]\n"
                f"    private IWebElement {key} {{ get; set; }} = null!;"
            )
            locators.append(f"        [{json.dumps(key)}] = () => {key}")
            methods.append(
                f"    public bool Is{key}Visible() => ControlVisible({json.dumps(key)});"
            )
            add(
                "regression",
                page_id,
                "control",
                label,
                f"{name}: {label} control is visible",
                selectorKey=key,
            )
            if control.get("tag") == "select" and control.get("options_json"):
                options = json.loads(control["options_json"])
                add(
                    "regression",
                    page_id,
                    "options",
                    json.dumps([option["text"] for option in options]),
                    f"{name}: {label} dropdown lists its published options",
                    selectorKey=key,
                )
                method = "Select" + key
                methods.append(
                    f"    public void {method}(string text)\n"
                    f"        => SelectOption({json.dumps(key)}, text);"
                )
                if label.casefold() in {"appearance", "theme", "color scheme", "colour scheme"}:
                    for option in options:
                        if not option.get("disabled"):
                            add(
                                "sanity",
                                page_id,
                                "selection",
                                option["text"],
                                f"{name}: select {option['text']} appearance",
                                selectorKey=key,
                            )
        body = (
            "using OpenQA.Selenium;\nusing SeleniumExtras.PageObjects;\n"
            "using Website.Automation.Models;\n\n"
            "namespace Website.Automation.Pages;\n\n"
            f"public sealed class {name}(IWebDriver driver, BrowserSettingsModel settings)\n"
            "    : BasePage(driver, settings)\n"
            "{\n"
            f"    public override string RelativePath => {json.dumps(path)};\n"
            + "\n".join(members)
            + "\n"
            "    protected override IReadOnlyDictionary<string, Func<IWebElement>>\n"
            "        ControlElements\n"
            "        => new Dictionary<string, Func<IWebElement>>\n"
            "    {\n" + ",\n".join(locators) + "\n    };\n" + "\n".join(methods) + "\n}\n"
        )
        if page.title:
            add(
                "smoke",
                page_id,
                "title",
                page.title,
                f"{name}: public page opens with title {page.title}",
            )
        else:
            add(
                "smoke",
                page_id,
                "document",
                "complete",
                f"{name}: public document finishes loading",
            )
        for heading in page.headings:
            add(
                "regression", page_id, "heading", heading, f"{name}: heading {heading} is displayed"
            )
        destinations: set[str] = set()
        actions, action_methods = [], []
        for link in page.links:
            destination = link["url"]
            target = targets.get(destination)
            if (
                destination == page.url
                or destination in destinations
                or target is None
                or not target.title
            ):
                continue
            if any(
                word in urlsplit(destination).path.casefold()
                for word in (
                    "logout",
                    "signout",
                    "delete",
                    "remove",
                    "unsubscribe",
                    "confirm",
                )
            ):
                continue
            destinations.add(destination)
            label = re.sub(r"^open\s+", "", link.get("text", ""), flags=re.I)
            method = "Open" + identifier(label, "Destination") + str(len(actions) + 1)
            actions.append(f"        [{json.dumps(destination)}] = {method}")
            action_methods.append(
                f"    public void {method}()\n"
                f"        => Navigation.FollowPublishedLink({json.dumps(destination)});"
            )
            add(
                "sanity",
                page_id,
                "navigation",
                destination,
                f"{name}: {link.get('text') or destination} opens the published destination",
                destinationUrl=destination,
                destinationTitle=target.title,
            )
        # A document readiness check is a technical browser contract, not a business rule.
        if not destinations:
            add(
                "sanity",
                page_id,
                "document",
                "complete",
                f"{name}: browser finishes loading the public document",
            )
        if not page.headings and not keys:
            add(
                "regression",
                page_id,
                "title" if page.title else "document",
                page.title or "complete",
                f"{name}: published document contract remains available",
            )

        navigation = (
            "    protected override IReadOnlyDictionary<string, Action> NavigationActions\n"
            "        => new Dictionary<string, Action>\n    {\n"
            + ",\n".join(actions)
            + "\n    };\n"
            + "\n".join(action_methods)
        )
        files[f"Pages/{name}.cs"] = body[:-2] + navigation + "\n}\n"

    files["Services/PageCatalogService.cs"] = (
        "using OpenQA.Selenium;\nusing SeleniumExtras.PageObjects;\n"
        "using Website.Automation.Models;\n"
        "using Website.Automation.Pages;\n\n"
        "namespace Website.Automation.Services;\n\n"
        "public sealed class PageCatalogService(\n"
        "    IWebDriver driver, BrowserSettingsModel settings)\n{\n"
        "    public BasePage Create(string id)\n    {\n"
        "        var pages = new Dictionary<string, Func<BasePage>>\n        {\n"
        + ",\n".join(registry)
        + "\n        };\n        var page = pages[id]();\n"
        "        PageFactory.InitElements(driver, page);\n        return page;\n    }\n}\n"
    )
    files["Input/PageObjects.Json"] = json.dumps(pages, ensure_ascii=False, indent=2)
    expectations = {
        "title": "its published page title is displayed",
        "heading": "its published heading is visible",
        "control": "its published control is visible",
        "navigation": "its published destination opens",
        "document": "its document finishes loading",
        "selection": "its published appearance option is selected",
        "options": "its published dropdown options are available",
    }
    for category, (feature, directory) in SUITES.items():
        lines = [
            f"Feature: {feature}",
            "  Public website checks derived from inspected evidence.",
            "",
        ]
        for case in (case for case in cases if case["category"] == category):
            action = {
                "navigation": "I follow its published navigation link",
                "selection": "I select its published appearance option",
            }.get(case["kind"], "I open its public page")
            lines.extend(
                [
                    f"  Scenario: {case['id']} - {case['title']}",
                    f'    Given the website scenario "{case["id"]}"',
                    f"    When {action}",
                    f"    Then {expectations[case['kind']]}",
                    "",
                ]
            )
        files[f"Features/{directory}/{directory}.feature"] = "\n".join(lines)
    return files, cases
