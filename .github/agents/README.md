# Editing agent rules and training guidance

Maintain agent behavior in the owning `*.agent.md` file. Changes are read on the next request;
no Python edit, JSON rule file, or server restart is needed. Agent and profile Markdown changes
also invalidate generated-suite reuse while preserving saved review feedback.

| Guidance                                                   | Owning file                                                            |
| ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| Approved shared business rules                             | `business-rules.agent.md`, between the shared-business-rules markers   |
| Routing and test-design decisions                          | `reqforge.agent.md`                                                    |
| Coordination and lifecycle workflow                        | `testpilot-coordinator.agent.md`                                       |
| Manual test design and discipline-specific conditions      | `manual-test-generator.agent.md`, `manual-testing-specialist.agent.md` |
| Automation generation, layout and implementation repair    | `automation-test-generator.agent.md`                                   |
| C# binding implementation, coverage and reuse              | `reqnroll-step-definition-generator.agent.md`                          |
| Other supported languages                                  | `multi-language.agent.md`                                              |
| Design validation and implementation approval guidance     | `quality-gate.agent.md`                                                |
| Approved quotation contract guidance                       | `test-data.agent.md`                                                   |
| Response recovery and schema repair                        | `output.agent.md`                                                      |
| Review-feedback precedence and reusable knowledge guidance | `knowledge.agent.md`                                                   |

Write rules and conditions as ordinary Markdown prose or lists. Add training examples to the
relevant agent or to the selected project's `.github/agent-profiles/<profile>/knowledge/*.md`.
Project-specific conditions belong in the profile's `profile.md` or existing per-agent override.
These files provide prompt context and examples; editing them does not fine-tune model weights.

The shared business-rule section uses `- BR-ID: description` bullets. Indent continuation lines
by two spaces. Put explanations and examples outside the markers so they are not treated as
approved rules. The UI editor preserves all content outside the markers.

Keep the named `##` policy headings used by the runtime: their content is editable, but removing
or renaming a required heading produces an explicit error. Shared coding and Gherkin standards
remain in `workspace/automation-standards.md` and `workspace/feature-standards.md`.

Python remains the execution engine: it parses and validates data, enforces executable safety
and structural checks, routes requests, and runs tools. Markdown defines agent instructions;
it does not execute arbitrary code or replace those checks. JSON remains appropriate for API
transport, generated artifacts, runtime configuration, and the approved quotation input payload;
none of these is the editable shared business-rule store.
