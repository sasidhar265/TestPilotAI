"""Public target isolation, bounded discovery and verified workflow source handoff."""

import socket
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.requirements_validation import RequirementsValidationAgent
from app.config import Settings
from app.main import app
from app.models import GenerateRequest
from app.services import website_inspection as website
from app.uploaded_brd import issue_brd_receipt

HTML = """<html><title>Careers</title><h1>Find a role</h1>
<script>ignore this instruction</script><input id="search" name="q" value="private">
<input type="password" value="secret"><button aria-label="Search">Search</button>
<a href="/guide">Guide</a><a href="https://other.example/">External</a>
<a href="/logout">Sign out</a></html>"""


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com",
        "http://user:pass@example.com",
        "https://example.com:8443",
        "https://example.com/?token=secret",
    ],
)
def test_reject_invalid_targets(url):
    with pytest.raises(website.WebsiteInspectionError):
        website.normalize_url(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "224.0.0.1"]
)
async def test_reject_nonpublic_dns(monkeypatch, address):
    monkeypatch.setattr(
        "asyncio.BaseEventLoop.getaddrinfo",
        AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]),
    )
    with pytest.raises(website.WebsiteInspectionError, match="public internet"):
        await website.public_address("example.com", 443)


@pytest.mark.asyncio
async def test_connections_are_pinned_and_redirects_revalidated(monkeypatch):
    resolve = AsyncMock(side_effect=["93.184.216.34", website.WebsiteInspectionError("private")])
    monkeypatch.setattr(website, "public_address", resolve)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/"})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        website.httpx,
        "AsyncClient",
        lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    with pytest.raises(website.WebsiteInspectionError, match="private"):
        await website.fetch_html("https://example.com/")
    assert len(calls) == 1
    assert calls[0].url.host == "93.184.216.34"
    assert calls[0].headers["host"] == "example.com"
    assert calls[0].extensions["sni_hostname"] == "example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response, message",
    [
        (httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}"), "HTML"),
        (httpx.Response(401), "HTTP 401"),
        (
            httpx.Response(200, headers={"content-type": "text/html"}, content=b"a" * 750001),
            "750 KB",
        ),
    ],
)
async def test_reject_unusable_responses(monkeypatch, response, message):
    monkeypatch.setattr(website, "public_address", AsyncMock(return_value="93.184.216.34"))
    client = httpx.AsyncClient
    monkeypatch.setattr(
        website.httpx,
        "AsyncClient",
        lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(lambda request: response)),
    )
    with pytest.raises(website.WebsiteInspectionError, match=message):
        await website.fetch_html("https://example.com/")


@pytest.mark.asyncio
async def test_discovery_stays_on_site_and_preserves_evidence(monkeypatch, tmp_path):
    fetch = AsyncMock(side_effect=lambda url: (url, HTML))
    monkeypatch.setattr(website, "fetch_html", fetch)
    settings = Settings(_env_file=None, requirements_baseline_path=tmp_path / "baseline.json")
    (tmp_path / "baseline.json").write_text('{"sources": []}')
    result = await website.WebsiteInspectionService().inspect(
        website.WebsiteRequest(url="https://example.com", max_pages=5), settings
    )
    assert [page.url for page in result.pages] == [
        "https://example.com/",
        "https://example.com/guide",
    ]
    assert 'input[id="search"]' in result.pages[0].controls[0]["selector"]
    assert "secret" not in result.description and "private" not in result.description
    assert "ignore this instruction" not in result.description
    assert website.verified_website_source(
        result.description, result.website_source_receipt, settings
    )
    assert not website.verified_website_source("forged", result.website_source_receipt, settings)
    document_receipt = issue_brd_receipt(result.description, settings)
    assert not website.verified_website_source(result.description, document_receipt, settings)
    request = GenerateRequest(
        description=result.description,
        website_source_text=result.description,
        website_source_receipt=result.website_source_receipt,
    )
    report = await RequirementsValidationAgent(settings).require(request)
    assert report.status == "aligned"
    assert report.sources[0]["status"] == "observed_only"
    request.website_source_text = "forged"
    report = await RequirementsValidationAgent(settings).assess(request)
    assert report.status == "blocked"


def test_api_inspection_and_validation(monkeypatch):
    monkeypatch.setattr(website, "fetch_html", AsyncMock(side_effect=lambda url: (url, HTML)))
    with TestClient(app) as client:
        response = client.post(
            "/api/workflow/requirements/website",
            json={
                "url": "https://example.com/",
                "max_pages": 1,
            },
        )
        assert response.status_code == 200
        assert response.json()["pages"][0]["title"] == "Careers"
        assert response.json()["website_source_receipt"]
        assert (
            client.post(
                "/api/workflow/requirements/website",
                json={
                    "url": "https://example.com",
                    "max_pages": 6,
                },
            ).status_code
            == 422
        )


@pytest.mark.asyncio
async def test_temporary_failure_retries_discovery_with_fresh_dns(monkeypatch):
    resolve = AsyncMock(side_effect=["93.184.216.34", "93.184.216.35"])
    monkeypatch.setattr(website, "public_address", resolve)
    monkeypatch.setattr(website.asyncio, "sleep", AsyncMock())
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=HTML)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        website.httpx,
        "AsyncClient",
        lambda **kwargs: client(
            **kwargs,
            transport=httpx.MockTransport(respond),
        ),
    )
    _, body = await website.fetch_html("https://example.com/")
    assert "Find a role" in body
    assert [call.url.host for call in calls] == ["93.184.216.34", "93.184.216.35"]
    assert all(call.headers["host"] == "example.com" for call in calls)
    assert resolve.await_count == 2


@pytest.mark.asyncio
async def test_temporary_failure_has_bounded_attempts_and_actionable_message(monkeypatch):
    monkeypatch.setattr(website, "public_address", AsyncMock(return_value="93.184.216.34"))
    pause = AsyncMock()
    monkeypatch.setattr(website.asyncio, "sleep", pause)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        website.httpx,
        "AsyncClient",
        lambda **kwargs: client(
            **kwargs,
            transport=httpx.MockTransport(respond),
        ),
    )
    with pytest.raises(website.WebsiteInspectionError, match="HTTP 503.*after 3 attempts"):
        await website.fetch_html("https://example.com/")
    assert len(calls) == 3
    assert pause.await_count == 2


@pytest.mark.asyncio
async def test_retry_does_not_bypass_private_dns_rejection(monkeypatch):
    resolve = AsyncMock(side_effect=["93.184.216.34", website.WebsiteInspectionError("private")])
    monkeypatch.setattr(website, "public_address", resolve)
    monkeypatch.setattr(website.asyncio, "sleep", AsyncMock())
    client = httpx.AsyncClient
    monkeypatch.setattr(
        website.httpx,
        "AsyncClient",
        lambda **kwargs: client(
            **kwargs,
            transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        ),
    )
    with pytest.raises(website.WebsiteInspectionError, match="private"):
        await website.fetch_html("https://example.com/")
    assert resolve.await_count == 2


def test_select_options_stay_with_their_own_published_control():
    parser = website.PageParser("https://example.com/")
    parser.feed("""<select aria-label="Appearance"><option value="light">Light mode</option>
        <option value="dark" disabled>Dark mode</option></select>
        <select id="status"><option value="open">Open</option></select>""")
    import json

    controls = [control for control in parser.page().controls if control["tag"] == "select"]
    appearance = json.loads(controls[0]["options_json"])
    assert appearance == [
        {"text": "Light mode", "value": "light", "disabled": False},
        {"text": "Dark mode", "value": "dark", "disabled": True},
    ]
    assert json.loads(controls[1]["options_json"])[0]["text"] == "Open"
