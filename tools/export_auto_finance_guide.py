"""Build the downloadable A4 reference PDF from the canonical single-file guide.

Run with the project's Playwright-enabled development environment:
    .venv/bin/python tools/export_auto_finance_guide.py
Chromium is needed at build time only; serving the PDF requires no browser.
"""

import hashlib
import io
import re
from pathlib import Path

from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/static/auto-finance-uk.html"
OUTPUT = SOURCE.with_suffix(".pdf")

PRINT_CSS = """
@page { size:A4; }
html { scroll-padding:0; }
body { font-size:10pt; line-height:1.45; background:white; }
header { min-height:235mm; padding:24mm 12mm; background:#123748!important;
  color:white!important; break-after:page; box-sizing:border-box; }
header .lede { color:#d4e4eb!important; font-size:13pt; line-height:1.7; }
header h1 { font-size:34pt; margin:25mm 0 12mm; }
header .meta { margin-top:18mm; gap:8px; }
header .meta span { color:white!important; border-color:#7898a6!important; font-size:9pt; }
header>a, aside, .actions, .toolbar, .skip, .check-status, body>footer { display:none!important; }
.layout { display:block; padding:0; }
section { break-before:page; padding:0; margin:0; border:0; border-radius:0; }
section h2 { font-size:23pt; margin:0 0 7mm; }
.eyebrow { color:#007b80; font-size:8pt; }
header .eyebrow { color:#bdeae2; }
h2,h3,h4,summary { break-after:avoid; }
p,li { orphans:3; widows:3; }
.card,details,.note,.glossary>div { break-inside:avoid; }
.grid { display:block; }
.card { margin:0 0 5mm; padding:5mm; border:1px solid #dce5ec; }
.card h3 { font-size:13pt; }
.card p { margin:2mm 0; }
.detail-grid { display:block; }
.detail-grid>div { margin-top:4mm; }
details { margin:5mm 0; padding:5mm; }
summary { font-size:13pt; list-style:none; }
summary::-webkit-details-marker { display:none; }
li { margin:1mm 0; }
.source { font-size:8pt; line-height:1.45; }
.source { break-before:avoid; }
.source a::after { content:none; }
a { color:#146086; overflow-wrap:anywhere; }
.table-wrap { overflow:visible; }
table { width:100%; min-width:0!important; font-size:9pt; table-layout:fixed; }
th,td { padding:3mm 2mm; overflow-wrap:anywhere; }
thead { display:table-header-group; }
tr { break-inside:avoid; }
.graph-shell { display:block; }
.network-panel { display:block!important; break-inside:avoid; }
.network-legend { display:flex!important; }
#topic-network { display:block!important; }
.mobile-network { display:none!important; }
.graph-scroll { break-inside:avoid; }
.graph-scroll svg { width:100%; min-width:0; }
.graph-detail { display:none; }
.glossary { display:block; }
.glossary>div { margin-bottom:4mm; }
.glossary dd { font-size:10pt; }
.contents { min-height:220mm; break-after:page; padding:10mm 0; }
.contents h2 { font-size:24pt; margin-bottom:12mm; }
.contents ol { list-style:none; padding:0; }
.contents li { display:flex; gap:5mm; align-items:baseline;
  border-bottom:1px solid #dce5ec; padding:3mm 0; }
.contents a { flex:1; text-decoration:none; color:#173447; }
.contents .page-number { font-variant-numeric:tabular-nums; }
#source-urls p { font-size:8pt; line-height:1.45; break-inside:avoid; }
* { print-color-adjust:exact; -webkit-print-color-adjust:exact; }
"""


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def locate_sections(reader: PdfReader, sections: list[dict]) -> dict[str, int]:
    pages = [normalize(page.extract_text()) for page in reader.pages]
    located = {}
    for section in sections:
        heading = normalize(section["title"])
        # Cover and contents also contain names; actual sections begin after them.
        matches = [index for index, text in enumerate(pages) if index > 1 and heading in text]
        if not matches:
            raise RuntimeError(f"Missing PDF section: {heading}")
        located[section["id"]] = matches[0]
    return located


def main() -> None:
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.goto(SOURCE.as_uri())
        page.locator("#graph-topic option").nth(11).wait_for(state="attached")
        sections = page.evaluate("""() => {
          document.querySelectorAll('details').forEach(el => el.open = true);
          document.querySelectorAll('[hidden]').forEach(el => el.hidden = false);
          document.querySelector('#graph .intro').textContent =
            'The graph shows quotation inputs on the left, the quote in the centre and '+
            'its downstream uses on the right. Labels explain each connection. The full '+
            'journey and relationship list follow. This authored domain map is '+
            'separate from the application’s saved requirement and test-coverage graph.';
          document.querySelector('#graph-overview>summary').textContent =
            'The full finance journey';
          document.querySelectorAll('.graph-node').forEach(el =>
            el.classList.remove('selected','related'));
          document.querySelectorAll('.graph-edge').forEach(el => el.classList.remove('selected'));
          const sections = [...document.querySelectorAll('main>section')].map(el =>
            ({id:el.id,title:el.querySelector('h2').textContent}));
          const contents = document.createElement('div'); contents.className = 'contents';
          const heading = document.createElement('h2'); heading.textContent = 'Contents';
          const list = document.createElement('ol');
          sections.forEach((section,index) => {
            const row = document.createElement('li');
            const link = document.createElement('a'); link.href = '#'+section.id;
            link.textContent = String(index+1).padStart(2,'0')+'  '+section.title;
            const number = document.createElement('span'); number.className = 'page-number';
            number.dataset.section = section.id; number.textContent = '00';
            row.append(link,number); list.append(row);
          });
          contents.append(heading,list); document.querySelector('header').after(contents);
          const sourceUrls = document.createElement('div'); sourceUrls.id = 'source-urls';
          const title = document.createElement('h3'); title.textContent = 'Full reference URLs';
          sourceUrls.append(title); const seen = new Set();
          document.querySelectorAll('a[href^="https://"]').forEach(link => {
            if (seen.has(link.href)) return; seen.add(link.href);
            const row = document.createElement('p');
            const label = document.createElement('strong'); label.textContent = link.textContent;
            const url = document.createElement('a');
            url.href = link.href; url.textContent = link.href;
            row.append(label,document.createElement('br'),url); sourceUrls.append(row);
          });
          document.querySelector('#sources').append(sourceUrls); return sections;
        }""")
        page.add_style_tag(content=PRINT_CSS)
        page.emulate_media(media="print")
        options = {
            "format": "A4", "print_background": True, "display_header_footer": True,
            "margin": {"top": "18mm", "bottom": "18mm", "left": "18mm", "right": "18mm"},
            "header_template": '<div style="font:8px Arial;color:#526b7b;width:100%;'
            'padding:0 18mm;">AUTO FINANCE · UK DOMAIN GUIDE</div>',
            "footer_template": '<div style="font:8px Arial;color:#526b7b;width:100%;'
            'padding:0 18mm;display:flex;justify-content:space-between;">'
            '<span>Reference v1.0 · 13 October 2026</span><span>Page '
            '<span class="pageNumber"></span> of <span class="totalPages"></span></span></div>',
        }
        draft = PdfReader(io.BytesIO(page.pdf(**options)))
        locations = locate_sections(draft, sections)
        page.evaluate("""locations => document.querySelectorAll('.page-number').forEach(el =>
          el.textContent = String(locations[el.dataset.section]+1))""", locations)
        final = PdfReader(io.BytesIO(page.pdf(**options)))
        if locate_sections(final, sections) != locations:
            raise RuntimeError("Contents pagination changed during final rendering")
        writer = PdfWriter(clone_from=final)
        writer.add_metadata({
            "/Title": "UK Auto Finance Domain Guide",
            "/Author": "Auto Finance Quality",
            "/Subject": "UK products, vehicle-to-contract journey and domain knowledge graph",
            "/SourceSHA256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        })
        for section in sections:
            writer.add_outline_item(section["title"], locations[section["id"]])
        with OUTPUT.open("wb") as output:
            writer.write(output)
        print(f"Created {OUTPUT.name}: {len(final.pages)} A4 pages, {len(sections)} bookmarks")
        browser.close()


if __name__ == "__main__":
    main()
