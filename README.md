# VaultTrace

**VaultTrace** is a secure document management platform with verified accounts, administrator approval, role-aware access, private document storage, explicit document sharing, version history, recoverable deletion, and document activity audit trails.

## 2. Project Overview

VaultTrace provides a React web client and a FastAPI JSON API backed by PostgreSQL. New users verify an email address and submit an application. An administrator reviews the application and assigns the Owner or Viewer role. Administrators explicitly assign users to organizations; existing accounts remain unassigned until this step. Owners can grant active, verified users in the same organization READ or EDIT access to individual documents, with optional expiration. FastAPI rechecks current account, organization, and grant state before protected document operations. Administrators can inspect document metadata and access audit events, but are not automatically granted file-content access. The backend stores file bytes in either a private local directory or a private Supabase bucket; PostgreSQL stores document metadata, organization membership, permissions, versions, and audit events.

Password-reset requests use a separate email OTP purpose. A successful reset requires a short-lived, single-use authorization and invalidates existing access tokens for that user.

## 3. Problem Statement

Systems that manage sensitive documents need reliable identity checks, explicit approval, server-enforced access roles, private file storage, and traceable administrative decisions. VaultTrace pairs those account controls with backend-authorized document operations and integrity checks.

## 4. Key Features

- Email-verified signup with a pending application and inactive account until approval.
- Administrator, Owner, and Viewer roles; role checks are enforced by the API.
- One-time Administrator bootstrap from environment configuration.
- Argon2 password hashing and signed, short-lived JWT access tokens.
- Purpose-separated signup and password-reset OTPs, hashed at rest and limited by expiry, attempt count, resend cooldown, and hourly send quota.
- SMTP email delivery with plain-text and HTML bodies; Mailpit support for local development.
- Administrator APIs for dashboard statistics, users, applications, approvals/rejections, role changes, account states, and audit records.
- Single-use password-reset authorization and access-token invalidation after password reset.
- Interchangeable private local filesystem and Supabase Storage providers for supported document formats, with server-side signature/MIME/size validation and UUID-based object keys.
- Authorized document search, category/date filters, pagination, metadata, backend-streamed downloads, and recoverable deletion.
- Explicit, expiring per-document READ/EDIT grants to active, verified users in the document owner's organization, immediate revocation, and sharing history. Legacy VIEWER/EDITOR records map to READ/EDIT. Legacy delegated OWNER grants do not confer permission administration or deletion.
- Administrator-only organization creation and user assignment. Membership is never inferred from email domains; existing users remain unassigned after migration.
- Document version history with retained previous versions, authorized historical downloads, soft deletion and owner restore.
- Document upload, owned/shared-with-me/shared-by-me/deleted, search, category, and administrator metadata/audit pages.
- Document activity records for uploads, reads/previews, sharing, permission changes/revocation, metadata changes, versions, deletion/restore, and denied access.
- Pytest integration/security tests, a Playwright smoke-test scaffold, and GitHub Actions checks.

Document access remains deny-by-default: non-owners need a current explicit grant, and visibility flags alone do not grant access. Owners upload and manage their own documents; Viewers see only documents explicitly shared with them. Administrators can view metadata and audit records and revoke grants, but cannot read document bytes through administrative APIs. Upload restrictions and supported formats are enforced by the backend.

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
  Models --> DB[(PostgreSQL metadata)]
  Services -->|Authorized private file operations| Storage[Local private directory or Supabase private bucket]
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
│   │       ├── 20261103_0003_email_verifications.py
│   │       ├── 20261103_0004_documents.py
│   │       ├── 20261104_0005_storage_provider.py
│   │       ├── 20261104_0006_user_updated_at.py
│   │       ├── 20261104_0007_user_updated_at_default.py
│   │       ├── 20261104_0008_document_access_versions.py
│   │       └── 20261104_0009_organizations.py
│   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── api/{__init__.py,dependencies.py}
│   │   │   ├── api/v1/{__init__.py,router.py,admin.py,documents.py}
│   │   ├── bootstrap_admin.py
│   │   ├── core/{__init__.py,config.py,security.py}
│   │   ├── db/{__init__.py,base.py,session.py}
│   │   ├── main.py
│   │   ├── models/{__init__.py,user.py,role.py,organization.py,registration_application.py,email_verification.py,otp_challenge.py,revoked_token.py,audit_log.py,document.py}
│   │   ├── schemas/{__init__.py,auth.py,admin.py,health.py,documents.py}
│   │   ├── seed_roles.py
│   │   ├── services/{__init__.py,auth.py,admin.py,registrations.py,otp.py,email.py,email_verifications.py,health.py,document_validation.py,documents.py,document_collaboration.py,storage.py}
│   │   └── utils/{__init__.py,identifiers.py}
│   └── tests/{__init__.py,client.py,conftest.py,database.py,test_auth_api.py,test_email_verifications.py,test_security.py,test_documents.py,test_storage_providers.py}
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
    │   ├── components/{AdminLayout.tsx,UserLayout.tsx,DocumentAccessDialog.tsx,DocumentPreviewDialog.tsx,OtpInput.tsx,OtpVerification.tsx,PasswordConfirmation.tsx,Placeholder.tsx}
    │   ├── context/AppContext.tsx
    │   ├── hooks/useHealth.ts
    │   ├── pages/{AdminApplicationsPage.tsx,AdminDashboardPage.tsx,AdminDocumentsPage.tsx,AdminUsersPage.tsx,DashboardPage.tsx,DocumentsPage.tsx,DocumentUploadPage.tsx,DocumentSearchPage.tsx,DocumentCategoriesPage.tsx,SharedWithMePage.tsx,SharedByMePage.tsx,DeletedDocumentsPage.tsx,ForgotPasswordPage.tsx,HomePage.tsx,LoginPage.tsx,ResetPasswordPage.tsx,SignupPage.tsx}
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
| `STORAGE_PROVIDER` | Selects `local` or `supabase`. Defaults to `local` outside production and `supabase` for `APP_ENV=production` if omitted; production explicitly rejects `local`. Selection never falls back when the chosen provider is unavailable. |
| `LOCAL_STORAGE_PATH` | Private backend-managed directory; defaults to `./private_storage`. It is ignored by Git, excluded from frontend static paths, and persisted by Compose through a private volume. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Backend-only Supabase project URL and service-role key. Required when `STORAGE_PROVIDER=supabase`; never expose either as a `VITE_` variable. |
| `SUPABASE_STORAGE_BUCKET` | Existing private bucket name; defaults to `vaulttrace-documents`. The backend refuses missing or public buckets. |
| `DOCUMENT_MAX_UPLOAD_BYTES`, `DOCUMENT_ALLOWED_EXTENSIONS` | Backend upload limit (default 5 MiB) and extension allowlist; the server validates content and MIME too. |
| `VITE_DOCUMENT_MAX_UPLOAD_BYTES`, `VITE_DOCUMENT_ALLOWED_EXTENSIONS` | Non-secret frontend hints for pre-upload size/extension feedback. The backend settings remain authoritative. |
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

The migrations create the roles/users/auth tables, registration applications and audit records, then purpose-scoped `email_verifications` and `password_reset_authorizations` tables and `users.token_version`. Commit 2 adds revisions `20261103_0004_documents` and `20261104_0005_storage_provider`. Revisions `20261104_0006_user_updated_at` and `20261104_0007_user_updated_at_default` add/populate the user update timestamp. Revision `20261104_0008_document_access_versions` adds per-document visibility, recoverable deletion, immutable versions, explicit permission grants, and document activity records; it backfills version 1 metadata for existing documents without changing document IDs or stored objects. Revision `20261104_0009_organizations` creates `organizations` and nullable `users.organization_id`; existing users are deliberately left unassigned. These additive revisions preserve existing user/document records and file bytes. Review the target database and back it up before applying migrations.

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
| `GET /admin/users` | Paginated user list with role, verification, state, registration date, and last update timestamp. |
| `GET /admin/applications` | Paginated applications, pending by default; filter `PENDING`, `APPROVED`, or `REJECTED`. |
| `GET /admin/applications/{application_id}` | Application details. |
| `POST /admin/applications/{application_id}/approve` | JSON body `{"role":"Owner"}` or `{"role":"Viewer"}`. Activates account and records reviewer/audit data. |
| `POST /admin/applications/{application_id}/reject` | JSON body `{"reason":"Review reason"}`. Deactivates account and records reviewer/reason/audit data. |
| `PATCH /admin/users/{user_id}/role` | JSON body `{"role":"Owner"}` or `{"role":"Viewer"}`. |
| `PATCH /admin/users/{user_id}/status` | JSON body `{"status":"ACTIVE"}`, `INACTIVE`, or `SUSPENDED`. |

Approval/rejection notifications are attempted by email; the action response reports whether notification delivery succeeded. Administrator roles cannot be assigned through the user role API, and administrator accounts are protected from these changes.

Account changes are persisted with an additive `users.updated_at` column (Alembic revision `20261104_0006`). Status and role updates use row locks scoped to the `users` table, audit the actor/target, previous and new values, timestamp, and successful result in the same transaction. These changes also increment `token_version`; the next request with an older JWT is rejected. Pending users may be activated only after email verification and application approval; rejected users cannot be reactivated through account management. Administrators and the acting administrator's own account are protected. Database exceptions return HTTP 503 with a safe connectivity message; raw connection details are not returned. Apply the migration before starting an app version that expects `updated_at`.

The older compatibility endpoints `POST /auth/otp/request`, `/auth/otp/resend`, and `/auth/otp/verify` are also present. New clients should use the purpose-specific signup endpoints above.

## 14. Authentication and Authorization Details

- Passwords are stored as Argon2 hashes using `pwdlib`; plaintext passwords are not persisted.
- Login issues a signed JWT access token (HS256 by default, 15-minute default lifetime). Send it as `Authorization: Bearer <token>`.
- Logout records the JWT ID as revoked. Password reset increments `users.token_version`, invalidating earlier access tokens for that user.
- FastAPI loads the current user from PostgreSQL and enforces role checks. Frontend route guards are for navigation only and are not an authorization boundary.
- Registration is public but requires an unexpired, verified signup proof; new users are `PENDING` and inactive until administrator approval.
- Roles are Administrator, Owner, and Viewer. Application approval can assign Owner or Viewer; public users cannot choose a role.
- The frontend keeps authentication state in React memory; it does not persist access tokens to local storage. Refreshing the page requires signing in again. No refresh-token API is currently implemented.

## Document management and authorization

PostgreSQL stores document metadata, the opaque storage key, and a `storage_provider` label. File bytes are in the selected provider. Set `STORAGE_PROVIDER=local` for local development; files go to `LOCAL_STORAGE_PATH` (default `./private_storage`), outside frontend public/static paths, with restrictive directory/file permissions. This directory is not mounted by an HTTP static route. Local provider keys are relative, traversal-checked, and generated from owner ID + UUID by the document service.

For deployment, set `STORAGE_PROVIDER=supabase`, create a **private** bucket called `vaulttrace-documents` (or set `SUPABASE_STORAGE_BUCKET`), and configure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` only in the backend environment. The Supabase provider refuses missing credentials or a missing/public bucket; it never falls back to local storage. Both providers implement the same upload/download/delete/exists interface. Each download/delete uses the provider stored on that specific document, so changing the selection affects new uploads without silently switching old records.

The default allowlist is PDF, PNG, JPEG, TXT, CSV, DOCX, and XLSX, with a 5 MiB maximum (`DOCUMENT_MAX_UPLOAD_BYTES` and `DOCUMENT_ALLOWED_EXTENSIONS`). The document service checks actual content signatures and supplied MIME type before calling either provider, uses owner ID + UUID keys, calculates SHA-256 checksums, and attempts cleanup if metadata persistence fails. Downloads are authorized and streamed by FastAPI. API metadata responses do not include provider names, bucket names, or storage keys.

Access is deny-by-default. An owner can share a document only with an active, verified registered account assigned to the same organization. The owner searches eligible recipients by email or username, then grants READ or EDIT with an optional expiration. Email domains do not establish membership. Administrators create organizations and explicitly assign/unassign user membership through `/admin/organizations` and `/admin/users/{user_id}/organization`. Existing users stay unassigned until an administrator performs that action; unassigned users cannot share or receive shared access. A public visibility label does not create public access; a current permission row and same-organization membership are both required. Revocation, expiry, organization mismatch, soft deletion, or changing visibility to `PRIVATE` removes access on the next backend authorization check. READ permits metadata, preview, download, and version history. EDIT also permits metadata edits and new versions. Only the actual document owner manages permissions, deletes/restores, and reviews document activity. Legacy `VIEWER`/`EDITOR` values are interpreted as READ/EDIT; legacy delegated `OWNER` grants provide at most EDIT and never permission administration or ownership. Administrator status alone does not allow reading document content. Current database state is checked on protected requests; no authorization cache is used.

| Method and path | Description |
| --- | --- |
| `POST /documents/upload` | Multipart fields: `file`, `document_name`, `category`, optional `description` and `visibility`; Owner role required. |
| `GET /documents/` | Documents owned by the caller; supports search, category/date, pagination, and sorting. |
| `GET /documents/search` | Search by UUID/name/original filename with category/type/owner/visibility/access/date filters; results are limited to owned and explicitly shared documents. |
| `GET /documents/categories`, `/shared-with-me`, `/shared-by-me`, `/deleted` | Authorized category, incoming grant, outgoing grant, or recoverable deletion lists. |
| `GET /documents/{document_id}` | Metadata for owner or a user with a live grant. |
| `GET /documents/{document_id}/eligible-users?q=...` | Active, verified accounts in the actual owner's organization; requires document ownership. |
| `GET /documents/{document_id}/preview` and `/download` | Authorized private stream; preview supports safe browser-renderable types, downloads verify checksums. |
| `PATCH /documents/{document_id}` | Change metadata; changing visibility to PRIVATE revokes active grants. |
| `GET/POST /documents/{document_id}/versions`, `GET /documents/{document_id}/versions/{version_id}/download` | List versions, upload a new immutable version, or download an authorized historical version. |
| `GET/POST /documents/{document_id}/permissions`, `PATCH/DELETE /documents/{document_id}/permissions/{permission_id}` | Actual owner lists, grants, updates, or revokes READ/EDIT access. Grant body takes `recipient_user_id`, a permission level, and optional `expires_at`. |
| `GET /documents/{document_id}/activity`, `POST /documents/{document_id}/restore`, `DELETE /documents/{document_id}` | Actual owner reviews activity, restores, or soft-deletes. Stored bytes remain private after soft-delete. |
| `GET /admin/documents`, `/admin/documents/permissions`, `/admin/documents/audit`, `DELETE /admin/documents/permissions/{permission_id}` | Administrator-only metadata/permission/audit review and emergency permission revocation; these routes do not return file bytes. |
| `GET/POST /admin/organizations`, `PATCH /admin/users/{user_id}/organization` | Administrator-only organization listing/creation and explicit user assignment (`{"organization_id": 7}`) or unassignment (`null`). |

Example:

```bash
curl 'http://localhost:8000/api/v1/documents/?category=finance&limit=20' \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Mocked provider tests need no Supabase credentials. `local` can be exercised with a private filesystem directory. Live Supabase upload/download requires a configured private bucket. Document collaboration tests use isolated SQLite and mocked storage. The live PostgreSQL migration and real storage-provider workflow must still be validated in the target development environment before release.

### Moving local files to Supabase

Provider migration is an explicit maintenance task; changing `STORAGE_PROVIDER` alone does not copy files. Stop writes or place the application in maintenance mode, back up PostgreSQL and the local storage directory, and verify every source object's size and checksum against its metadata. Copy each local object's bytes to the same UUID-based `storage_key` in the private Supabase bucket. Verify the destination bytes/checksum before updating that document row's `storage_provider` to `supabase` and `storage_bucket` to the configured bucket in a transaction. Keep IDs and all other metadata unchanged. Resume writes only after verifying migrated rows; remove local copies only after a separate backup/retention period. On any copy or verification failure, leave the database row labeled `local` and retry or roll back the copied destination object. For a large library, implement a reviewed resumable migration tool before starting this process.

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

The checked-in Playwright tests cover sign-in/signup, role-specific dashboard navigation and redirects, distinct upload/search/category pages, and the Shared With Me empty state. The current GitHub Actions workflow runs backend bytecode compilation and frontend build; it does not run Pytest or Playwright. Browser tests require Node.js 20 or newer and an environment that allows the local Vite server to bind to its configured loopback address.

## 16. Docker Setup

Docker Compose includes `mailpit`, `backend`, and `frontend`. It intentionally has no PostgreSQL service. The backend connects to the PostgreSQL server configured in `.env`; on Linux the backend container uses host networking. Local private files persist in the ignored `./private_storage` bind mount. Mailpit publishes SMTP `1025` and inbox UI `8025`; the frontend development server publishes `5173`.

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
- Private document workspace: _screenshot pending_

## 19. Troubleshooting and Common Errors

| Symptom | Check |
| --- | --- |
| PostgreSQL connection refused/no response | Start the existing PostgreSQL service and check `pg_isready -h localhost -p 5432`. Do not replace existing credentials with sample values. |
| Account update returns a generic failure | Ensure PostgreSQL is accepting connections, inspect the backend log/HTTP status, and apply pending Alembic migrations. Status/role updates need a reachable database; the UI displays API error details or the HTTP status when no detail is returned. |
| `Could not reach the VaultTrace API` / no API response | Start Uvicorn and confirm `curl http://127.0.0.1:8000/health` returns JSON. A browser network error means there is no HTTP response; it is different from API 401/403/404/500 responses. The API client now reports the configured base URL and timeout separately. |
| `password authentication failed` | Confirm `DATABASE_URL` uses the correct PostgreSQL role/password/database. URL-encode reserved characters in the password. Test with `psql -h localhost -U USER -d DB_NAME -W` to prompt securely. |
| OTP endpoint returns database/migration 503 | Check PostgreSQL auth/connectivity, then check `PYTHONPATH=backend python -m alembic -c backend/alembic.ini current` and migrate the intended database if needed. |
| OTP email delivery unavailable | Check Mailpit/provider host, port, TLS mode, sender, and backend process environment. For local Mailpit, open `http://localhost:8025`; it captures mail and does not forward it. |
| OTP request returns 429 | Observe `Retry-After`; the default resend cooldown is 60 seconds and hourly quota is 5 requests per email. |
| Document upload reports storage unavailable | Check `STORAGE_PROVIDER`. For `local`, confirm `LOCAL_STORAGE_PATH` is writable and outside static directories; for `supabase`, check backend-only credentials and that the configured bucket exists and is private. |
| Document upload is rejected | Check the configured extension allowlist, maximum byte limit, file signature, and MIME type; backend validation is authoritative. |
| Signup returns 422 | Read the JSON `detail` in the response. Check valid email, 3–32 character username pattern, 12–128 character password, matching confirmation, and field length limits. |
| Signup returns 409 although the email is new | Confirm the username is also unused. If both are new, check `alembic current` and apply pending migrations: PostgreSQL needs the `users.updated_at` default from revision `20261104_0007`; older databases may report a misleading duplicate message for that schema error. |
| Browser reports network/CORS failure | Confirm API at port 8000, frontend origin matches `FRONTEND_ORIGIN`, and `VITE_API_BASE_URL` points to `/api/v1`. CORS allows GET/POST/PATCH/DELETE/OPTIONS. |
| `ModuleNotFoundError: app` | Run commands from repository root with `PYTHONPATH=backend` (PowerShell: `$env:PYTHONPATH = "backend"`) or use Uvicorn's `--app-dir backend`. |
| Mailpit page does not open | Ensure Docker is running and run `docker compose up -d mailpit`; check that port 8025 is not already occupied. |
| Playwright cannot launch Chromium | Run `npx playwright install chromium` from `frontend/`. |

## 20. Security Considerations

- Never commit `.env`, SMTP credentials, JWT/OTP secrets, or bootstrap passwords. `.env.example` contains placeholders only.
- Use unique random JWT and OTP HMAC secrets and a strong, unique administrator password. The bootstrap command never resets an existing account.
- OTPs are cryptographically generated, purpose-scoped, HMAC-hashed at rest, time-limited, rate-limited, attempt-limited, and single-use. Reset authorizations are random, short-lived, single-use, and stored as hashes.
- Do not log OTPs, passwords, JWTs, reset authorizations, or SMTP credentials. Use HTTPS and a trusted SMTP provider outside local development.
- Authorization must be checked by FastAPI; frontend routes/role values are not security controls. Every document request needs ownership or a current explicit grant. Supabase must remain private; only the backend uses the service-role secret. The browser receives neither storage keys nor permanent URLs.
- Keep test data synthetic. Review `THREATS.md` and conduct a security review before handling real documents or deploying.

## 21. Future Enhancements

Possible future work includes retention policies, malware scanning, production SMTP hardening, hardened production containers, broader browser/E2E coverage, and deployment-specific monitoring/backups.

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

- [`PROMPTS.md`](PROMPTS.md): Commit 1–3 prompts, implementation inventories, and AI-assisted development workflow.
- [`THREATS.md`](THREATS.md): Implementation threat model and remaining review items.
