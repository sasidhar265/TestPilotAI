# Local development with Microsoft User Secrets

The Python application and C# BDD project can share the same Microsoft User Secrets
store. The project declares `UserSecretsId=quality-lifecycle-studio-local`. No secrets
are included in the project file or committed to the repository.

Enable local loading in your shell:

```bash
export ENVIRONMENT=development
export USER_SECRETS_ENABLED=true
```

For the Python app, `USER_SECRETS_ENABLED=true` can also be set in `.env`.
Direct `dotnet test` reads environment variables and User Secrets, not `.env`.
Loading is off by default and disabled outside `ENVIRONMENT=development` even when
`USER_SECRETS_ENABLED` is true. Render continues to use its environment variables.

Set values with Microsoft's CLI, using the application's existing configuration names:

```bash
dotnet user-secrets set API_AUTH_TOKEN '<your-local-token>' --project automation/QualityLifecycle.Automation.csproj
dotnet user-secrets set APP_USERNAME '<your-local-username>' --project automation/QualityLifecycle.Automation.csproj
dotnet user-secrets set APP_PASSWORD '<your-local-password>' --project automation/QualityLifecycle.Automation.csproj
dotnet user-secrets set SESSION_SECRET '<your-local-session-secret>' --project automation/QualityLifecycle.Automation.csproj
dotnet user-secrets set QUALITY_LIFECYCLE_BASE_URL 'http://127.0.0.1:8000' --project automation/QualityLifecycle.Automation.csproj
```

Other existing settings, such as `OPENAI_API_KEY`, `GEMINI_API_KEY`, `API_BASE_URL`,
`API_BEARER_TOKEN`, and `JIRA_API_TOKEN`, use the same flat uppercase names. The Python
loader accepts case-insensitive field names. Use flat keys, not nested sections.

Microsoft stores the local `secrets.json` at:

- macOS/Linux: `~/.microsoft/usersecrets/quality-lifecycle-studio-local/secrets.json`
- Windows: `%APPDATA%\Microsoft\UserSecrets\quality-lifecycle-studio-local\secrets.json`

The file can also be edited locally as a JSON object. It is a development convenience,
not encrypted secret storage. Do not use it as the production secret manager.

Python configuration precedence is explicit constructor values, environment variables,
User Secrets, `.env`, then defaults. For direct C# execution, environment variables
precede User Secrets. An explicitly empty environment variable also overrides a stored
value; unset that variable if you want to use the secret. Local secrets override `.env`
values, so existing empty `.env` placeholders do not mask them.

Start the app and run the existing BDD suite:

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
dotnet test automation/QualityLifecycle.Automation.csproj
```

Run those commands in separate terminals with the same opt-in environment. For direct
BDD execution, configure `API_AUTH_TOKEN` to match the app. The in-app Run BDD action
also supports browser-session authentication when no bearer token is configured.
The in-app runner resolves settings once and forwards only the required values to its
child process; it disables reloading of User Secrets in that child.

Restart the app after editing secrets; its settings and the C# configuration are cached
for each process. For an alternate store, set `USER_SECRETS_ID` and use the matching
`dotnet user-secrets --id <identifier>` option. The environment selection and opt-in
controls are never taken from the secrets file itself.

Existing credentials are not migrated automatically. Remove obsolete copies from `.env`
only after verifying the new store with your local application.

Reference: [Microsoft: safe storage of app secrets in development](https://learn.microsoft.com/aspnet/core/security/app-secrets).
