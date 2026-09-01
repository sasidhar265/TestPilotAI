# Security policy

Report suspected vulnerabilities privately to the repository's organization security contact.
Do not open a public issue containing credentials, prompts, customer requirements, Jira data, or
exploit details.

## Security requirements

- Never commit `.env`, GitHub credentials, Jira tokens, or generated customer data.
- Use synthetic test data only.
- Keep Copilot tools and workspace mutation disabled during generation.
- Treat model output as untrusted and validate it before rendering or export.
- Keep Jira publishing explicit and least privileged.
- Rotate a credential immediately if it appears in source, logs, chat, or CI output.
- Treat `.agent-memory/test_suites.db` as organizational data. Keep it out of Git and apply the
  deployment environment's access, encryption, retention, backup, and deletion controls.

## Production boundary

The container is an internal upstream, not a public authentication endpoint. Place it behind the
company's TLS-terminating identity-aware proxy, restrict network access to that proxy, and have the
proxy inject the server-side bearer token configured as `API_AUTH_TOKEN`. Use explicit
`ALLOWED_HOSTS`; never configure `*` in production.

The application rejects oversized and overly expansive document archives, but this is not malware
scanning. Production ingress must quarantine uploads and pass them through the organization's
malware/content-disarm service before forwarding them. Rotate the upstream bearer token and all
provider credentials through the approved secret manager.
