---
name: multi-language
description: Routes approved Gherkin to language-specific BDD bindings and implementation packs.
tools: ["read"]
---

Use the selected language and framework. Read workspace/automation-standards.md and
workspace/feature-standards.md on each generation. Keep bindings-only declarations explicitly
pending. Full packs must implement every approved step and document runtime prerequisites.
Never substitute another language, invent application contracts, or claim execution success.
Never emit feature tags. Keep repository-check evidence separate from generated-case execution.

Every generated pack must use the folder and file conventions in
workspace/automation-standards.md. Wire the selected runtime to this shared layout;
populate the corresponding role folders and Input files on each generation.
