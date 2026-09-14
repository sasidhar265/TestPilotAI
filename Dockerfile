FROM mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim AS dotnet
FROM python:3.12-slim-bookworm AS runtime

COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOTNET_ROOT=/usr/share/dotnet \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    AUTOMATION_SKIP_BUILD=true \
    NUGET_PACKAGES=/srv/nuget \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/usr/share/dotnet:/opt/allure/bin:${PATH}"

RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr libicu72 libssl3 curl ca-certificates default-jre-headless \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --create-home app

WORKDIR /srv/app
COPY pyproject.toml README.md ./
COPY app ./app
COPY workspace ./workspace
COPY .github/agents ./.github/agents
COPY .github/agent-profiles ./.github/agent-profiles
RUN python -m pip install .

COPY automation ./automation
# Restore and build during deployment; runtime tests use --no-build --no-restore.
RUN dotnet build automation/QualityLifecycle.Automation.csproj \
    && dotnet tool install --tool-path /opt/powershell PowerShell --version 7.4.6 \
    && /opt/powershell/pwsh automation/bin/Debug/net8.0/playwright.ps1 install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

ARG ALLURE_VERSION=2.32.0
RUN curl --fail --location --retry 3 \
      "https://github.com/allure-framework/allure2/releases/download/${ALLURE_VERSION}/allure-${ALLURE_VERSION}.tgz" \
      --output /tmp/allure.tgz \
    && mkdir -p /opt/allure \
    && tar -xzf /tmp/allure.tgz --strip-components=1 -C /opt/allure \
    && rm /tmp/allure.tgz \
    && allure --version

RUN mkdir -p /srv/app/.agent-memory && chown -R app:app /srv/app /srv/nuget
USER app

EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '10000') + '/api/ready', timeout=2)"]

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --no-server-header --timeout-graceful-shutdown 30"]
