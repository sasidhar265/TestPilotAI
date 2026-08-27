# TestPilot project profile

Apply these project-specific rules in addition to the mandatory base agent policies:

- Inputs may be stories or BRDs extracted from DOCX, PDF, XLSX, Pages, Numbers, PNG, or JPEG.
- Use only the categories `critical`, `smoke`, `sanity`, and `regression`.
- Preserve `AC-*` and `BR-*` identifiers for end-to-end traceability.
- Generate synthetic data only; never expose credentials or customer data.
- Keep manual and automation feasibility explicit and risk-based.
- Approved outputs must remain compatible with Xray CSV/XLSX/JSON and Jira workflows.
- Jira publication always requires an explicit user action.
