FROM python:3.13-slim

# Active variant: Docker Compose controls startup order and runs
# migration/app commands via `command` in docker-compose.yaml.
# This image only installs dependencies and application code.
ENV APP_HOME=/app \
    POETRY_VERSION=2.3.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    SUPERCRONIC_VERSION=v0.2.29

WORKDIR $APP_HOME

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Supercronic so a dedicated scheduler container can run periodic jobs.
RUN curl -fsSLo /usr/local/bin/supercronic \
    https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64 \
    && chmod +x /usr/local/bin/supercronic

COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION" \
    && poetry install --only main --no-root

COPY . .
EXPOSE 8000
