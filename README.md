# VaultTrace

**VaultTrace** is a secure document-sharing platform foundation focused on verified accounts, administrator approval, role-aware access, and audit trails. The current Commit 1 implements account and access-management workflows. Document upload, storage, sharing, and document-level permissions are not implemented yet.

## 2. Project Overview

VaultTrace provides a React web client and a FastAPI JSON API backed by PostgreSQL. New users verify an email address and submit an application. An administrator reviews the application and assigns the Owner or Viewer role. Administrators can inspect users, manage permitted roles and account states, and review audit records through the administrative APIs.

Password-reset requests use a separate email OTP purpose. A successful reset requires a short-lived, single-use authorization and invalidates existing access tokens for that user.

## 3. Problem Statement

Systems that share sensitive documents need reliable identity checks, explicit approval, server-enforced access roles, and traceable administrative decisions. VaultTrace establishes those account and access-control foundations before adding document workflows.

## 4. Key Features

- Email-verified signup with a pending application and inactive account until approval.
- Administrator, Owner, and Viewer roles; role checks are enforced by the API.
- One-time Administrator bootstrap from environment configuration.
- Argon2 password hashing and signed, short-lived JWT access tokens.
- Purpose-separated signup and password-reset OTPs, hashed at rest and limited by expiry, attempt count, resend cooldown, and hourly send quota.
- SMTP email delivery with plain-text and HTML bodies; Mailpit support for local development.
- Administrator APIs for dashboard statistics, users, applications, approvals/rejections, role changes, account states, and audit records.
- Single-use password-reset authorization and access-token invalidation after password reset.
- Pytest integration/security tests, a Playwright smoke-test scaffold, and GitHub Actions checks.

Document storage, document sharing, and document-level authorization are future work and are not part of this release.

## 5. Technology Stack

| Area | Technology |
| --- | --- |
| Backend runtime/API | Python 3.12, FastAPI, Uvicorn |
| Validation/configuration | Pydantic 2, pydantic-settings, email-validator |
| Persistence | PostgreSQL, SQLAlchemy 2, Psycopg 3 |
| Schema migrations | Alembic |
| Authentication/security | JWT via `python-jose`, Argon2 via `pwdlib`, HMAC OTP digests |
| Backend tests | Pytest, HTTPX, AnyIO; in-memory SQLite test database |
| Frontend | React 18, TypeScript, Vite, React Router, Axios |
| Styling | Tailwind CSS, PostCSS, Autoprefixer |
| Browser tests | Playwright with TypeScript |
| Local email | Mailpit over SMTP |
| Containers/CI | Docker, Docker Compose, GitHub Actions |

## 6. System Architecture

```mermaid
flowchart LR
  Browser[React + TypeScript + Vite] -->|JSON API / Bearer JWT| API[FastAPI API v1]
  API --> Services[Authentication and admin services]
  Services --> Models[SQLAlchemy models]
  Models --> DB[(Existing PostgreSQL database)]
  Services --> SMTP[SMTP provider or local Mailpit]
  API -->|Alembic schema revisions| DB
```

The backend is layered into API routes, dependencies/security, database access, ORM models, Pydantic schemas, and service modules. Routes validate/translate HTTP requests; registration, OTP, authentication, and administrator business logic resides in services. The frontend calls the API through `frontend/src/services/api.ts`.

## 7. Project Folder Structure

```text
VaultTrace/
├── .env.example
├── .github/workflows/ci.yml
├── .gitignore
├── LICENSE
├── PROMPTS.md
├── README.md
├── THREATS.md
├── docker-compose.yml
├── requirements.txt
├── backend/
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 20261103_0001_auth_foundation.py
│   │       ├── 20261103_0002_registration_admin.py
│   │       └── 20261103_0003_email_verifications.py
│   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── api/{__init__.py,dependencies.py}
│   │   │   ├── api/v1/{__init__.py,router.py,admin.py}
│   │   ├── bootstrap_admin.py
│   │   ├── core/{__init__.py,config.py,security.py}
│   │   ├── db/{__init__.py,base.py,session.py}
│   │   ├── main.py
│   │   ├── models/{__init__.py,user.py,role.py,registration_application.py,email_verification.py,otp_challenge.py,revoked_token.py,audit_log.py}
│   │   ├── schemas/{__init__.py,auth.py,admin.py,health.py}
│   │   ├── seed_roles.py
│   │   ├── services/{__init__.py,auth.py,admin.py,registrations.py,otp.py,email.py,email_verifications.py,health.py}
│   │   └── utils/{__init__.py,identifiers.py}
│   └── tests/{__init__.py,client.py,conftest.py,database.py,test_auth_api.py,test_email_verifications.py,test_security.py}
└── frontend/
    ├── Dockerfile
    ├── e2e/smoke.spec.ts
    ├── index.html
    ├── package.json
    ├── package-lock.json
    ├── playwright.config.ts
    ├── postcss.config.js
    ├── src/
    │   ├── App.tsx
    │   ├── main.tsx
    │   ├── styles.css
    │   ├── vite-env.d.ts
    │   ├── components/{AdminLayout.tsx,OtpInput.tsx,OtpVerification.tsx,PasswordConfirmation.tsx,Placeholder.tsx}
    │   ├── context/AppContext.tsx
    │   ├── hooks/useHealth.ts
    │   ├── pages/{AdminApplicationsPage.tsx,AdminDashboardPage.tsx,AdminUsersPage.tsx,DashboardPage.tsx,ForgotPasswordPage.tsx,HomePage.tsx,LoginPage.tsx,ResetPasswordPage.tsx,SignupPage.tsx}
    │   ├── services/api.ts
    │   ├── types/index.ts
    │   └── utils/format.ts
    ├── tailwind.config.js
    ├── tsconfig.json
    └── vite.config.ts
```

There is no PostgreSQL service in `docker-compose.yml`; development uses an existing local PostgreSQL server. Brace groups above abbreviate sibling files. `PasswordResetAuthorization` is a model class in `email_verification.py`, not a separate file.

## 8. Prerequisites and Software Requirements

- Python 3.12.
- PostgreSQL server and a database/role accessible to the configured `DATABASE_URL`.
- Node.js 20 or newer and npm.
- Git.
- Optional: Docker Engine/Desktop with the Compose plugin for Mailpit and the development containers.

## 9. Installation Instructions

Clone the repository and open a terminal in the repository root. Do not replace an existing `.env` or change an existing PostgreSQL username, password, or database just to match the examples.

Create a Python virtual environment and install backend dependencies.

**Linux/macOS:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**Windows PowerShell:**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, allow it for the current terminal only with `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again.

Install frontend dependencies from `frontend/`:

```bash
cd frontend
npm ci
```

PowerShell uses the same `cd frontend` and `npm ci` commands.

## 10. Environment Variable Configuration (`.env.example`)

Create `.env` only if one does not already exist:

```bash
# Linux/macOS
test -f .env || cp .env.example .env
```

```powershell
# Windows PowerShell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit `.env` locally. Replace placeholders with values for your environment; generate unique random `JWT_SECRET_KEY` and `OTP_HASH_SECRET` values. Do not commit `.env` or paste its contents into issues. `.gitignore` ignores `.env*` while allowing `.env.example`.

| Variable | Purpose |
| --- | --- |
| `APP_NAME`, `APP_ENV` | Application label and environment label. |
| `API_HOST`, `API_PORT` | API host/port settings; the local Uvicorn command below supplies explicit values. |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL, e.g. `postgresql+psycopg://USER:PASSWORD@localhost:5432/DB_NAME`. Use the actual existing local PostgreSQL credentials. URL-encode reserved characters in the password. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Reference placeholders for manually provisioning a local database; the Compose file does not define a PostgreSQL service and the backend connects through `DATABASE_URL`. |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT signing configuration; the default algorithm is HS256 and default access-token lifetime is 15 minutes. |
| `OTP_HASH_SECRET` | Separate secret used to HMAC OTPs; the code falls back to the JWT secret if this is unset. Configure a distinct random value. |
| `OTP_EXPIRATION_MINUTES`, `OTP_MAX_ATTEMPTS`, `OTP_RESEND_COOLDOWN_SECONDS`, `OTP_MAX_SENDS_PER_HOUR` | OTP expiry and rate-limit configuration; defaults are 5 minutes, 5 attempts, 60 seconds, and 5 sends/hour. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | Backend SMTP connection and optional authentication. Mailpit defaults are host `localhost`, port `1025`, with no credentials. |
| `SMTP_FROM`, `SMTP_STARTTLS`, `SMTP_USE_SSL` | SMTP sender and legacy TLS/SSL configuration passed by the current Compose backend service. |
| `SMTP_FROM_EMAIL`, `SMTP_USE_TLS` | Sender/TLS configuration aliases read by the backend when running directly. Use the correct TLS mode for the selected SMTP provider. |
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | Lifetime of reset authorization; default is 10 minutes. |
| `ADMIN_BOOTSTRAP_EMAIL`, `ADMIN_BOOTSTRAP_USERNAME`, `ADMIN_BOOTSTRAP_PASSWORD`, `ADMIN_BOOTSTRAP_FULL_NAME` | Credentials/profile for the explicit initial-admin bootstrap command. The password must be at least 12 characters. The command creates an administrator only if none exists and does not reset existing admins. |
| `FRONTEND_ORIGIN`, `VITE_API_BASE_URL` | Backend CORS origin and frontend API base URL; defaults target local Vite/FastAPI ports. |

For SMTP, Mailpit is a local capture service: messages appear in its web inbox and are not forwarded to a real mailbox. For real delivery, configure a legitimate SMTP provider in the backend environment. Never put SMTP credentials in Vite variables or frontend source.

## 11. Database Setup and Migration

Use an existing PostgreSQL database when available. For a **new, empty development database only**, connect to PostgreSQL as an administrator and create a role/database (choose and securely set a password interactively):

```sql
CREATE ROLE vaulttrace LOGIN;
\password vaulttrace
CREATE DATABASE vaulttrace OWNER vaulttrace;
```

Then set `DATABASE_URL` in `.env` to use that role/database. Do not run the creation statements against an existing production or shared database. If a password contains URL-reserved characters, URL-encode it in `DATABASE_URL`.

Check connectivity before migrating:

```bash
pg_isready -h localhost -p 5432
```

Apply the current Alembic revisions from the repository root:

```bash
# Linux/macOS
PYTHONPATH=backend python -m alembic -c backend/alembic.ini upgrade head
```

```powershell
# Windows PowerShell
$env:PYTHONPATH = "backend"
python -m alembic -c backend/alembic.ini upgrade head
```

The migrations create the roles/users/auth tables, registration applications and audit records, then the purpose-scoped `email_verifications` and `password_reset_authorizations` tables and `users.token_version`. They are additive at the latest revision and do not remove existing user rows. Review the target database and back it up before production migrations.

Seed missing built-in roles (idempotent):

```bash
# Linux/macOS
PYTHONPATH=backend python -m app.seed_roles
```

```powershell
# Windows PowerShell; set PYTHONPATH in the same terminal first
$env:PYTHONPATH = "backend"
python -m app.seed_roles
```

## 12. How to Run the Project Locally

Start Mailpit if you want to inspect locally generated OTP emails:

```bash
docker compose up -d mailpit
```

Mailpit SMTP is `localhost:1025`; the inbox UI is `http://localhost:8025`. If Docker is unavailable, configure another reachable SMTP server or email sends will fail.

Configure the bootstrap administrator values in `.env`, then run the bootstrap once. If an administrator already exists, bootstrap reports that no change was made.

**Linux/macOS, from the repository root:**

```bash
source .venv/bin/activate
PYTHONPATH=backend python -m app.bootstrap_admin
PYTHONPATH=backend python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
```

**Windows PowerShell, from the repository root:**

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "backend"
python -m app.bootstrap_admin
python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. The API is at `http://localhost:8000`; interactive OpenAPI documentation is at `http://localhost:8000/docs`; health check is `http://localhost:8000/health`. The backend does not automatically run Alembic migrations at application startup; apply migrations explicitly first.

### Single-command development containers

After PostgreSQL is running, `.env` is configured, and migrations/bootstrap are complete, Docker Compose can start the configured development services with:

```bash
docker compose up --build
```

This starts Mailpit, the FastAPI container, and the Vite development container. It does **not** start PostgreSQL. The backend uses `network_mode: host`; this is designed around Linux host networking and may need networking changes on Docker Desktop for Windows/macOS. For those platforms, the local Python/Node commands above are the documented path. The container images run development servers, not production serving stacks.

## 13. API Documentation with Examples

All versioned routes use `http://localhost:8000/api/v1`. OpenAPI UI is available at `/docs` while the backend runs.

### Authentication and signup

| Method and path | Authentication | Purpose |
| --- | --- | --- |
| `POST /auth/signup/send-otp` | Public | Request a signup OTP. Returns a generic message; the OTP is delivered by email, never in the response. |
| `POST /auth/signup/verify-otp` | Public | Verify a six-digit signup OTP. |
| `POST /auth/register` | Public, but requires verified email proof | Create an inactive PENDING account/application. |
| `POST /auth/login` | Public | Authenticate and receive a bearer access token. Pending, rejected, inactive, or suspended accounts cannot log in. |
| `POST /auth/logout` | Bearer token | Revoke the current access token. |
| `GET /users/me` | Bearer token | Return the current user profile. |
| `POST /auth/forgot-password` | Public | Send a reset OTP where eligible; response is generic to avoid email enumeration. |
| `POST /auth/verify-reset-otp` | Public | Verify the reset OTP and receive a short-lived reset authorization. |
| `POST /auth/reset-password` | Reset authorization in request body | Consume authorization and set a new password. |
| `GET /health` | Public, outside `/api/v1` | Return process health status. |

Example signup OTP request (Linux/macOS; replace the example address):

```bash
curl -X POST http://localhost:8000/api/v1/auth/signup/send-otp \
  -H 'Content-Type: application/json' \
  -d '{"email":"person@example.com"}'
```

Windows PowerShell equivalent:

```powershell
$body = @{ email = 'person@example.com' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/auth/signup/send-otp' -Method Post -ContentType 'application/json' -Body $body
```

OTP verification body:

```json
{"email":"person@example.com","otp":"123456"}
```

Registration body (send only after successful OTP verification):

```json
{
  "full_name": "Example Person",
  "username": "example-person",
  "email": "person@example.com",
  "phone_number": null,
  "password": "replace-with-a-12-character-or-longer-password",
  "confirm_password": "replace-with-a-12-character-or-longer-password"
}
```

Passwords are validated to 12–128 characters and confirmation must match. User role is not accepted from the public registration payload. A successful response has HTTP 201 and includes the application ID and `PENDING` status.

Login request:

```json
{"email":"admin@example.com","password":"your-local-admin-password"}
```

The response includes `access_token`, `token_type`, expiry, and public user data including role. Use the token in protected API requests:

```bash
curl http://localhost:8000/api/v1/admin/dashboard \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Reset request bodies:

```json
{"email":"person@example.com"}
```

```json
{"email":"person@example.com","otp":"123456"}
```

```json
{
  "authorization_token": "token-returned-by-verify-reset-otp",
  "password": "new-password-at-least-12-characters",
  "confirm_password": "new-password-at-least-12-characters"
}
```

### Administrator APIs

All `/admin` routes require an authenticated Administrator. User and application list APIs accept `limit` (1–100, default 50) and `offset` (default 0). `GET /admin/applications` filters `approval_status` and defaults to `PENDING`.

| Method and path | Description |
| --- | --- |
| `GET /admin/dashboard` | PostgreSQL-backed counts: registered, active, pending, approved, rejected, Owners, and Viewers. |
| `GET /admin/users` | Paginated user list with role, verification, state, and registration date. |
| `GET /admin/applications` | Paginated applications, pending by default; filter `PENDING`, `APPROVED`, or `REJECTED`. |
| `GET /admin/applications/{application_id}` | Application details. |
| `POST /admin/applications/{application_id}/approve` | JSON body `{"role":"Owner"}` or `{"role":"Viewer"}`. Activates account and records reviewer/audit data. |
| `POST /admin/applications/{application_id}/reject` | JSON body `{"reason":"Review reason"}`. Deactivates account and records reviewer/reason/audit data. |
| `PATCH /admin/users/{user_id}/role` | JSON body `{"role":"Owner"}` or `{"role":"Viewer"}`. |
| `PATCH /admin/users/{user_id}/status` | JSON body `{"status":"ACTIVE"}`, `INACTIVE`, or `SUSPENDED`. |

Approval/rejection notifications are attempted by email; the action response reports whether notification delivery succeeded. Administrator roles cannot be assigned through the user role API, and administrator accounts are protected from these changes.

The older compatibility endpoints `POST /auth/otp/request`, `/auth/otp/resend`, and `/auth/otp/verify` are also present. New clients should use the purpose-specific signup endpoints above.

## 14. Authentication and Authorization Details

- Passwords are stored as Argon2 hashes using `pwdlib`; plaintext passwords are not persisted.
- Login issues a signed JWT access token (HS256 by default, 15-minute default lifetime). Send it as `Authorization: Bearer <token>`.
- Logout records the JWT ID as revoked. Password reset increments `users.token_version`, invalidating earlier access tokens for that user.
- FastAPI loads the current user from PostgreSQL and enforces role checks. Frontend route guards are for navigation only and are not an authorization boundary.
- Registration is public but requires an unexpired, verified signup proof; new users are `PENDING` and inactive until administrator approval.
- Roles are Administrator, Owner, and Viewer. Application approval can assign Owner or Viewer; public users cannot choose a role.
- The frontend keeps authentication state in React memory; it does not persist access tokens to local storage. Refreshing the page requires signing in again. No refresh-token API is currently implemented.

## 15. Testing Instructions

Backend tests use an isolated in-memory SQLite database and mock SMTP. They do not use your development PostgreSQL database or send email.

```bash
# Linux/macOS, from repo root with the venv activated
PYTHONPATH=backend python -m pytest backend/tests -q
```

```powershell
# Windows PowerShell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
```

Frontend production build/typecheck:

```bash
cd frontend
npm run build
```

Playwright smoke tests (the config starts the Vite dev server):

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

The checked-in Playwright tests cover the sign-in page and that signup requires email verification before submission. The current GitHub Actions workflow runs backend bytecode compilation and frontend build; it does not run Pytest or Playwright.

## 16. Docker Setup

Docker Compose includes `mailpit`, `backend`, and `frontend`. It intentionally has no PostgreSQL service. The backend connects to the PostgreSQL server configured in `.env`; on Linux the backend container uses host networking. Mailpit publishes SMTP `1025` and inbox UI `8025`; the frontend development server publishes `5173`.

Validate Compose configuration and start the development stack:

```bash
docker compose config --quiet
docker compose up --build
```

For just local email capture:

```bash
docker compose up -d mailpit
```

Use Docker Engine/Desktop with Compose installed and running. The checked-in Dockerfiles run Uvicorn and Vite development servers; do not treat this Compose file as a hardened production deployment.

## 17. Live Deployment Instructions

No live deployment target, hosting-provider configuration, production reverse proxy, or production Compose file is included. A deployment cannot be launched from this repository with a verified provider-specific command.

Before deploying, an operator should provision PostgreSQL and SMTP, configure secrets outside the repository, run reviewed Alembic migrations as a release step, serve a production frontend build from a static web server/CDN, run the API behind an HTTPS reverse proxy, configure exact CORS origins, backups, monitoring, and recovery procedures, and use production server/container settings rather than the development Dockerfiles. Validate role-change `PATCH` requests and CORS configuration for the chosen deployment topology before release.

## 18. Demo Screenshots

Screenshots are not currently included. Add reviewed, synthetic-data screenshots here when available; do not publish real user addresses, tokens, OTPs, or private document data.

- Sign-in: _screenshot pending_
- Signup and email verification: _screenshot pending_
- Administrator dashboard: _screenshot pending_
- Application review: _screenshot pending_

## 19. Troubleshooting and Common Errors

| Symptom | Check |
| --- | --- |
| PostgreSQL connection refused/no response | Start the existing PostgreSQL service and check `pg_isready -h localhost -p 5432`. Do not replace existing credentials with sample values. |
| `password authentication failed` | Confirm `DATABASE_URL` uses the correct PostgreSQL role/password/database. URL-encode reserved characters in the password. Test with `psql -h localhost -U USER -d DB_NAME -W` to prompt securely. |
| OTP endpoint returns database/migration 503 | Check PostgreSQL auth/connectivity, then check `PYTHONPATH=backend python -m alembic -c backend/alembic.ini current` and migrate the intended database if needed. |
| OTP email delivery unavailable | Check Mailpit/provider host, port, TLS mode, sender, and backend process environment. For local Mailpit, open `http://localhost:8025`; it captures mail and does not forward it. |
| OTP request returns 429 | Observe `Retry-After`; the default resend cooldown is 60 seconds and hourly quota is 5 requests per email. |
| Signup returns 422 | Read the JSON `detail` in the response. Check valid email, 3–32 character username pattern, 12–128 character password, matching confirmation, and field length limits. |
| Browser reports network/CORS failure | Confirm API at port 8000, frontend origin matches `FRONTEND_ORIGIN`, and `VITE_API_BASE_URL` points to `/api/v1`. Current CORS allows GET/POST/OPTIONS but not PATCH; cross-origin admin role/status updates can fail preflight until configuration is updated. |
| `ModuleNotFoundError: app` | Run commands from repository root with `PYTHONPATH=backend` (PowerShell: `$env:PYTHONPATH = "backend"`) or use Uvicorn's `--app-dir backend`. |
| Mailpit page does not open | Ensure Docker is running and run `docker compose up -d mailpit`; check that port 8025 is not already occupied. |
| Playwright cannot launch Chromium | Run `npx playwright install chromium` from `frontend/`. |

## 20. Security Considerations

- Never commit `.env`, SMTP credentials, JWT/OTP secrets, or bootstrap passwords. `.env.example` contains placeholders only.
- Use unique random JWT and OTP HMAC secrets and a strong, unique administrator password. The bootstrap command never resets an existing account.
- OTPs are cryptographically generated, purpose-scoped, HMAC-hashed at rest, time-limited, rate-limited, attempt-limited, and single-use. Reset authorizations are random, short-lived, single-use, and stored as hashes.
- Do not log OTPs, passwords, JWTs, reset authorizations, or SMTP credentials. Use HTTPS and a trusted SMTP provider outside local development.
- Authorization must be checked by FastAPI; frontend routes/role values are not security controls. Review CORS and the documented PATCH limitation before using a cross-origin deployment.
- Keep test data synthetic. Review `THREATS.md` and conduct a security review before handling real documents or deploying.

## 21. Future Enhancements

Planned work beyond this foundation may include document upload/storage, document-level Owner/Viewer authorization, secure sharing, versioning, retention, and document-access audit trails. These are not implemented in Commit 1. Other operational follow-up includes production SMTP, hardened production containers, broader browser/E2E coverage, and deployment-specific monitoring/backups.

## 22. Contribution Guidelines

1. Open an issue describing the problem and proposed scope before broad changes.
2. Preserve the existing layered structure; keep business rules in services and route logic in `backend/app/api/v1`.
3. Add/update Pytest tests for backend behavior and Playwright tests for user-facing flows; do not use real secrets or personal data in fixtures.
4. Update README/environment examples when behavior or setup changes. Never edit a contributor’s local `.env` as part of a routine feature change.
5. Run backend tests, frontend build, and relevant migration/configuration checks; include actual command results in the pull request.
6. Request focused review for authentication, authorization, cryptography, migrations, email, and deployment changes. Do not commit generated secrets or production data.

## 23. License

VaultTrace is distributed under the MIT License. See [`LICENSE`](LICENSE).

## Project Documentation

- [`PROMPTS.md`](PROMPTS.md): Commit 1 prompt, implementation inventory, and AI-assisted development workflow.
- [`THREATS.md`](THREATS.md): Initial threat-model template.
