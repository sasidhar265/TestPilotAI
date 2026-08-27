# Frontend guide

The frontend deliberately uses plain HTML, CSS, and JavaScript so it can be read
without learning a framework first.

## Where to start

Each webpage has three matching files:

| Page | Structure | Appearance | Behaviour |
| --- | --- | --- | --- |
| Test Designer | `index.html` | `styles/index.css` | `scripts/index.js` |
| Application Guide | `documentation.html` | `styles/documentation.css` | `scripts/documentation.js` |

Read them from left to right:

1. Open the HTML to see which elements appear on the page.
2. Search for an element's `class` in the matching CSS file to see its styling.
3. Search for its `id` in the matching JavaScript file to see its behaviour.

## How the browser loads these files

FastAPI returns `index.html` for `/` and `documentation.html` for
`/documentation`. Each HTML file then loads its own stylesheet and script from
the `/static` route configured in `app/main.py`.

The JavaScript calls backend URLs beginning with `/api/`. Keeping those URLs in
the script makes it easy to trace a button click from the browser to the
corresponding FastAPI route.
