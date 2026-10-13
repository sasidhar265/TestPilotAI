## Mandatory provider model policy

Every LLM-backed agent must use GPT-6-ASTRA (`gpt-6-astra`) when executing through
Codex AI / Codex CLI, and Claude Haiku 4.5 (`claude-haiku-4.5`) when executing through
GitHub Copilot. This applies to coordinators, specialists, generation, evaluation,
framework creation, retries and repair calls. Runtime model selection enforces this rule;
prompts cannot select a different model.

Never use account defaults, automatic model selection or substitute models within these
providers. Copilot's legacy `auto` and `organization-default` route names resolve to
Claude Haiku 4.5. Other explicitly requested Copilot models are rejected. If the required
model is inaccessible, report the provider failure. The existing explicitly selected
multi-provider fallback workflow may continue to its next provider, using the same mandatory
assignment whenever it reaches Codex or Copilot. Explicit Codex/Copilot suite requests must
not silently switch providers. OpenAI API and Gemini routes retain their own configuration.

Carry the explicitly selected provider through business analysis, requirements alignment,
stories, scenarios, test cases and automation-pack generation. Retries and repairs stay on
that provider. Only `auto-fallback` permits switching providers; Copilot aliases `auto` and
`organization-default` select Copilot with Claude Haiku 4.5 and do not enable cross-provider fallback.

For explicit Codex, OpenAI API or Gemini generation, lifecycle coordination uses the
application's local validation/storage workflow rather than making an additional Copilot
coordinator call. The selected provider performs the AI generation.
