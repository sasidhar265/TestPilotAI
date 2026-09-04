FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl tesseract-ocr \
    && curl -fsSL https://chatgpt.com/codex/install.sh -o /tmp/install-codex.sh \
    && sh /tmp/install-codex.sh \
    && install -m 0755 /root/.local/bin/codex /usr/local/bin/codex \
    && rm -f /tmp/install-codex.sh \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --create-home app

WORKDIR /srv/app
COPY pyproject.toml README.md ./
COPY app ./app
COPY .github/agents ./.github/agents
COPY .github/agent-profiles ./.github/agent-profiles
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN python -m pip install .

RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /srv/app/.agent-memory \
    && chown -R app:app /srv/app
USER app

EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '10000') + '/api/ready', timeout=2)"]

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
