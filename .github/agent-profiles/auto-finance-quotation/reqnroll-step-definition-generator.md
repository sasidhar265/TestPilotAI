# UK Quotation Services ReqnRoll policy

Apply the profile's scope and source-precedence rules. Use its BRD v1.0 baseline for applicable
quotation semantics not supplied by the current requirements. Generate bindings only for
the supplied Quality Gate-approved automation Gherkin; the BRD validates applicable meanings and expected
contracts but is not permission to invent additional scenarios, endpoints, payload fields, or
calculation formulas.

Support reusable bindings for every supplied BRD validation scenario, including canonical request
construction from the user-approved QuotationRequest.Json using QuotationRequestBuilder,
configured invalid/missing/boundary/effective-date test
data, and assertions for all supplied business errors. Typed response assertions cover `status`,
exact `code`, safe `message`, optional `field`, `correlationId`, and absence of stack traces or
confidential calculation details.

Keep financial values as C# `decimal`; deserialize into typed quotation/error records. Represent
brand, product, customer type, maintenance option, quote date, expected code, and oracle/version
fields as typed parameters or transformations when reused. Do not hard-code 20% VAT, eligibility
limits, rates, APR, residuals, fees, maintenance prices, CAC, expected payments, service URLs, or
credentials. Approved golden/reference data belongs in injected fixtures or Examples-derived
scenario data.

The coverage map must preserve each scenario's supplied requirement traceability (including
`BR-QT-*` when applicable) in the artifact notes and
classify every unique validation step as reused, generated, or blocked. Missing runtime values use
the base policy's configurable implementation contract. Missing business semantics are blocked,
never guessed. Never emit placeholder methods.

For supplied domain steps, implement the following operations through typed approved configuration:

- Outcome/canonical/error assertions: resolve the named outcome to an expected HTTP status and
  nonempty expected JSON field comparisons; assert correlation evidence, approved safe error
  fields, and absence of configured confidential fields. Do not treat a nonempty response as success.
- Boundary/invalid/catalogue fixtures: select the exact approved fixture variant by the supplied
  parameters and load its request, version expectations and expected outcome. Do not invent
  boundary values or mutate a real environment. Verify pinned versions from observable evidence.
- Repeated submissions: send the same request twice, preserve both responses, and compare the
  configured deterministic fields against each other and independent approved version values.
- Oracle/decimal checks: load versioned approved golden outputs and nonempty decimal field/shape
  mappings; compare using decimal arithmetic and an explicitly configured approved tolerance.
- Access/audit checks: select an approved access-state fixture and credentials, submit the actual
  request, and assert configured audit evidence and absence of unauthorized calculation output.
  If separate audit evidence is required, implement a configured evidence query and verify it;
  do not infer audit success solely from the response status.
- Load checks: use an approved, bounded request count/concurrency and catalogue, execute actual
  requests, record elapsed times and failures, and calculate mean and nearest-rank P95. Enforce
  the supplied 1s/2s limits; do not discard failures or invent exceptions. Require independently
  verifiable pinned-environment evidence, not a configuration flag asserting the environment is pinned.

Document missing runtime configuration in notes while still returning concrete implementations
for all implementable bindings. Keep assertions tied to the full meaning of each supplied step.


The user-approved request contract overrides older BRD payload examples: only Outlet, Finance,
Vehicle and Parameters and their exact supplied fields are request body members. The application
includes the complete JSON in generation instructions. Keep strategy selection, fixture parsing,
validation and branching in services. Step definitions contain no if/else, switch or ternary
operators and delegate to the builder via scenario context/services. Use the supplied
ApprovedQuotationRequestStrategy for defaults and ConfiguredQuotationRequestStrategy with typed
builder overrides for explicit test data. Do not construct anonymous alternative request bodies.
