# Photo Share REST API

REST API for photo sharing built with FastAPI, async SQLAlchemy, PostgreSQL,
Redis, Cloudinary, JWT authentication, email verification, password reset,
role-based access control, and photo transformation workflows.

## Features

- User signup and signin
- JWT access tokens + refresh token rotation
- Refresh token stored in `HttpOnly` cookie
- Email confirmation after signup
- Resend email confirmation flow
- Password reset by email with one-time DB-backed token state
- Logout of current session
- Logout from all devices
- Redis-backed blacklist for revoked access tokens
- Public and private user profile endpoints
- Admin user management:
  - change role
  - block/unblock users
- Photo upload to Cloudinary
- Avatar upload to Cloudinary
- Photo search by text or tag
- Optional photo filtering by:
  - author username
  - rating range
  - date range
- Photo tags
- Photo comments
- Photo ratings
- Photo transformation preview with Pillow
- Saved transformed photo URLs + QR codes
- Rate limiting with Redis buckets
- Docker Compose setup for local infrastructure
- Daily cleanup job for old password reset tokens

## Tech Stack

- Python 3.13
- FastAPI
- SQLAlchemy 2.x async
- Alembic
- PostgreSQL
- Redis
- Poetry
- Docker / Docker Compose
- Cloudinary
- Pillow
- QRCode
- FastAPI-Mail
- Brevo API
- Pytest

## Architecture

Project is organized by layers:

- `src/routes` - FastAPI endpoints
- `src/services` - business logic and external integrations
- `src/repository` - database access
- `src/entity` - SQLAlchemy models
- `src/schemas` - Pydantic request/response schemas
- `src/config` - settings, middleware, handlers, rate limiters
- `src/scripts` - standalone maintenance scripts

Main domain entities:

- `User`
- `UserSession`
- `PasswordResetToken`
- `Photo`
- `Tag`
- `PhotoTransformation`
- `Comment`
- `PhotoRating`

## Local vs Deploy

This project uses two different operational approaches.

### Local Development

Typical local setup:

- PostgreSQL in Docker Compose or local PostgreSQL
- Redis in Docker Compose or local Redis
- SMTP email delivery through `fastapi-mail`
- `EMAIL_PROVIDER=smtp`
- `COOKIE_SECURE=false`
- direct local DB connection, usually on port `5432`
- plain Redis connection, usually `redis://`-style host/port settings

Typical local values:

```env
PSG_DB_DOMAIN=localhost
PSG_DB_PORT=5432
REDIS_DOMAIN=localhost
REDIS_PORT=6379
EMAIL_PROVIDER=smtp
COOKIE_SECURE=false
```

### Deploy / Production

Typical deployed setup:

- managed PostgreSQL, for example Supabase pooler
- managed Redis, for example Upstash
- HTTPS email delivery through Brevo API
- `EMAIL_PROVIDER=brevo_api`
- `COOKIE_SECURE=true`
- Redis usually works through TLS / `rediss://default`
- DB may use pooler port `6543`

Important production-specific behavior already implemented:

- if DB port is `6543` or DB host contains `pooler`, statement cache is
  disabled for asyncpg to avoid PgBouncer / pooler issues
- Redis client enables SSL automatically when `REDIS_URL` starts with
  `rediss://`
- access/refresh cookie behavior is controlled by `COOKIE_SECURE`

## Environment Variables

Create `.env` in project root.

Base variables:

```env
PSG_DB_USER=postgres
PSG_DB_PASSWORD=postgres
PSG_DB_NAME=photo_share
PSG_DB_DOMAIN=localhost
PSG_DB_PORT=5432

SECRET_KEY=replace_with_random_secret_key
HASH_ALGORITHM=HS256

MAIL_USERNAME=mailtrap_user
MAIL_PASSWORD=mailtrap_password
MAIL_FROM=test@example.com
MAIL_PORT=2525
MAIL_SERVER=sandbox.smtp.mailtrap.io
MAIL_STARTTLS=true
MAIL_SSL_TLS=false
MAIL_FROM_NAME=Photo Share API

EMAIL_PROVIDER=smtp
BREVO_API_KEY=

REDIS_DOMAIN=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_URL=redis://localhost:6379/0

CLOUDINARY_NAME=cloud_name
CLOUDINARY_API_KEY=12345678
CLOUDINARY_API_SECRET=api_secret
CLOUDINARY_PUBLIC_ID_PREFIX=photo_share

FRONTEND_URL=http://localhost:3000
COOKIE_SECURE=false
TESTING=false
```

Notes:

- local SMTP flow uses `MAIL_*` settings with `EMAIL_PROVIDER=smtp`
- deployed Brevo flow uses `EMAIL_PROVIDER=brevo_api` and `BREVO_API_KEY`
- local Redis can work with plain host/port
- deployed Redis can use `REDIS_URL=rediss://...`
- `COOKIE_SECURE` should be `false` locally and `true` in production

Example production-specific differences:

```env
PSG_DB_DOMAIN=your-supabase-pooler-host
PSG_DB_PORT=6543

EMAIL_PROVIDER=brevo_api
BREVO_API_KEY=your_brevo_api_key

REDIS_URL=rediss://default:password@host:port/0

COOKIE_SECURE=true
```

## Installation

Install dependencies:

```bash
poetry install
```

Install dev + test dependencies:

```bash
poetry install --with dev,test
```

## Run Locally with Poetry

1. Configure `.env`
2. Start PostgreSQL and Redis
3. Apply migrations
4. Run the API

Commands:

```bash
poetry run alembic upgrade heads
poetry run uvicorn main:app --reload
```

Application URLs:

- App: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Health endpoints:

- `GET /`
- `GET /api/healthchecker`

## Run with Docker Compose

Start the local stack:

```bash
docker compose up --build -d
```

Services defined in `docker-compose.yaml`:

- `db` - PostgreSQL
- `redis` - Redis
- `migrate` - Alembic migrations
- `app_server` - FastAPI app
- `cleanup_scheduler` - daily password reset token cleanup

Useful commands:

```bash
docker compose logs -f
docker compose down
docker compose down -v
```

If you want to run migrations explicitly:

```bash
docker compose run --rm migrate
```

If you want to run the cleanup script manually:

```bash
docker compose exec app_server poetry run python -m src.scripts.cleanup_password_reset_tokens
```

## Migrations

Create migration:

```bash
poetry run alembic revision --autogenerate -m "message"
```

Apply migrations locally:

```bash
poetry run alembic upgrade heads
```

Apply migrations in Docker:

```bash
docker compose run --rm migrate
```

Current migration chain includes:

- initial schema
- photos, tags, transformations
- display name
- comments
- photo ratings
- user sessions
- unique constraint for password reset token per user
- timezone-aware timestamp migration

## Email Delivery

Two email delivery modes are supported.

### Local

- provider: `smtp`
- implementation: `fastapi-mail`
- intended for Mailtrap or another SMTP sandbox

### Deploy

- provider: `brevo_api`
- implementation: direct HTTPS call to Brevo transactional email API
- useful when hosting blocks outbound SMTP

Templates:

- `src/services/templates/verify_email.html`
- `src/services/templates/reset_password.html`

## Authentication Flow

1. `POST /api/auth/signup`
2. Confirm email through `GET /api/auth/confirm-email/{token}`
3. `POST /api/auth/signin`
4. Use `Authorization: Bearer <access_token>` for protected endpoints
5. Refresh auth through `POST /api/auth/refresh`
6. Logout through `POST /api/auth/logout`

Important:

- `refresh_token` is stored in an `HttpOnly` cookie
- browser clients must send refresh requests with `credentials included`
- `POST /api/auth/refresh` reads refresh token from cookie, not from bearer header

## Password Reset Flow

1. `POST /api/auth/password-reset/request`
2. `GET /api/auth/password-reset/verify/{token}`
3. `PATCH /api/auth/password-reset/confirm`

Security details:

- API returns generic response from reset request endpoint even if email does
  not exist
- raw reset token is never stored in DB, only its SHA-256 hash
- only one active reset token row exists per user
- token is checked against:
  - JWT validity
  - DB existence
  - `used_at`
  - `expires_at`
- token becomes unusable after successful password change

## Sessions and Logout

Session model:

- access token contains `jti`
- refresh token hash is stored in `user_sessions`
- access token `jti` is also stored in `user_sessions`

Logout behavior:

- current access token is blacklisted in Redis until JWT expiration
- current refresh-token session can be deleted
- all sessions can be deleted through logout-from-all-devices
- blocking a user removes all persisted sessions for that user

## Redis Blacklist Check

To verify that logout adds the access token to Redis blacklist:

1. start Redis and the API
2. sign in
3. call `POST /api/auth/logout`
4. open Redis CLI:

```bash
docker exec -it redis redis-cli
```

5. check blacklist keys:

```redis
KEYS blacklist:access:*
```

6. inspect TTL:

```redis
TTL blacklist:access:<jti>
```

## Rate Limiting

Rate limiters are defined in `src/config/rate_limiters.py`.

Current limits:

- auth base: `20/min`
- signup: `5/min`
- refresh token: `5/min`
- confirm email: `5/min`
- request confirm email: `1/3 min`
- password reset request: `1/12 hours`
- user base: `20/min`
- user profile update: `1/60 sec`
- photo base: `20/min`
- photo upload: `5/min`
- photo preview generation: `5/min`
- photo transformation save: `5/min`
- comment base: `20/min`
- photo rating base: `20/min`

In tests, rate limiting is disabled and in-memory limiter buckets are used at
import time to avoid Redis dependency during pytest startup.

## User Roles

Available roles:

- `admin`
- `moderator`
- `user`

Important behavior:

- first registered account becomes `admin`
- only admin can change another user's role
- admin cannot assign `admin` role through public API
- admin cannot manage self through admin management endpoints
- admin cannot manage another admin through those endpoints
- staff-level access means `admin` or `moderator`

## Validation Notes

- request validation errors are normalized to `400` by custom global handler
- signup password requirements:
  - 8 to 16 chars
  - one lowercase letter
  - one uppercase letter
  - one digit
  - one special char from `!@#$%^&*`
- username:
  - 3 to 30 chars
  - must start with lowercase letter
  - only lowercase letters, digits, underscores
  - must not end with underscore
- display name:
  - 2 to 60 chars in form input
  - letters, spaces, hyphens, apostrophes
- photo tags:
  - up to 5 tags
  - each tag max 50 chars
  - tags must be unique after normalization
- photo descriptions max length: `300`
- comment max length: `300`
- photo rating range: `1..5`

## Tests

Test stack:

- unit tests for repository and service layers
- integration route tests with `TestClient`
- route tests use dedicated SQLite test DB and FastAPI dependency overrides

Install test dependencies:

```bash
poetry install --with test
```

Run all tests:

```bash
poetry run pytest -v tests
```

Run one route test file:

```bash
poetry run pytest -v tests/integration/routes/test_auth_routes.py
```

Run service unit tests:

```bash
poetry run pytest -v tests/unit/services
```

Run repository unit tests:

```bash
poetry run pytest -v tests/unit/repositories
```

Test directories:

- `tests/unit/repositories`
- `tests/unit/services`
- `tests/integration/routes`

## API Routes

### Health

- `GET /`
- `GET /api/healthchecker`

### Auth Routes

Base prefix: `/api/auth`

- `POST /signup` - register a new user
- `POST /signin` - authenticate user and issue access token + refresh cookie
- `POST /logout` - logout current session
- `POST /logout-from-all-devices` - logout all sessions for current user
- `GET /confirm-email/{token}` - confirm email
- `POST /request-confirm-email` - resend confirmation email
- `POST /refresh` - rotate refresh token and issue new access token
- `POST /password-reset/request` - request password reset email
- `GET /password-reset/verify/{token}` - validate reset token
- `PATCH /password-reset/confirm` - confirm password reset

### User Routes

Base prefix: `/api/users`

- `GET /me` - get current authenticated user info
- `GET /all` - paginated public user profiles
- `GET /profile/{username}` - public profile by username
- `GET /profile` - editable own profile
- `PATCH /profile` - update own profile, supports avatar upload
- `PATCH /role/{user_id}` - change user role, admin only
- `PATCH /{user_id}/blocked` - block/unblock user, admin only

### Photo Routes

Base prefix: `/api/photos`

- `POST /` - upload photo
- `GET /{photo_id}` - get photo by id
- `GET /user/{user_id}` - get paginated photos of a user
- `GET /` - filtered photo search
- `DELETE /{photo_id}` - delete photo
- `PUT /{photo_id}/description` - update description
- `PATCH /{photo_id}/tags` - replace tags
- `POST /{photo_id}/transform-preview` - generate local preview
- `POST /{photo_id}/transformations` - save transformation + QR code
- `GET /{photo_id}/transformations` - list saved transformations for photo
- `GET /transformations/{transformation_id}` - get one transformation

### Comment Routes

Base prefix: `/api/photos`

- `POST /{photo_id}/comments` - create comment
- `GET /{photo_id}/comments` - paginated photo comments
- `PATCH /{photo_id}/comments/{comment_id}` - update own comment
- `DELETE /{photo_id}/comments/{comment_id}` - delete comment, staff only

### Photo Rating Routes

Base prefix: `/api/photos`

- `POST /{photo_id}/rating` - create rating for photo
- `GET /{photo_id}/ratings` - paginated ratings list, staff only
- `GET /ratings/{rating_id}` - get one rating, staff only
- `DELETE /ratings/{rating_id}` - delete rating, staff only

## Project Structure

```text
photo-share-rest-api/
  main.py
  pyproject.toml
  alembic.ini
  docker-compose.yaml
  Dockerfile
  .env.example
  .env.prod
  info.md
  scripts/
    cleanup-cron
  src/
    config/
      handlers.py
      messages.py
      middlewares.py
      rate_limiters.py
      settings.py
    database/
      db.py
    entity/
      comment.py
      models.py
      photo.py
      photo_rating.py
      user.py
    helpers/
      create_exception.py
    migrations/
      env.py
      versions/
    repository/
      auth.py
      comment.py
      photo.py
      photo_rating.py
      user.py
    routes/
      auth.py
      comment.py
      photo.py
      photo_rating.py
      user.py
    schemas/
      auth.py
      comment.py
      photo.py
      photo_rating.py
      user.py
    scripts/
      cleanup_password_reset_tokens.py
    services/
      auth.py
      comment.py
      email.py
      photo.py
      redis_client.py
      role.py
      token_blacklist.py
      user.py
      templates/
        reset_password.html
        verify_email.html
  tests/
    conftest.py
    integration/
      routes/
    unit/
      repositories/
      services/
```

## Notes

- `README.md` is declared in `pyproject.toml`, so it must exist in the repo
- `postgres-photo_share_api-schema.png` can be used as ERD/reference image
