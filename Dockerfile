FROM python:3.13-slim

# Active variant: Docker Compose controls startup order and runs
# migration/app commands via `command` in docker-compose.yaml.
# This image only installs dependencies and application code.
ENV APP_HOME=/app \
    POETRY_VERSION=2.3.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR $APP_HOME

COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION" \
    && poetry install --only main --no-root

COPY . .
EXPOSE 8000
