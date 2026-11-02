# AI-assisted development workflow

## Email OTP and reset workflow

- Signup and password-reset OTPs are purpose separated in the PostgreSQL `email_verifications` table. Store keyed OTP digests only; never include OTPs in logs or frontend persistence.
- SMTP comes from environment variables `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and `SMTP_USE_TLS`. Do not paste actual SMTP credentials into prompts, source, or docs.
- Local development can use Mailpit on `localhost:1025`; browse its inbox at `http://localhost:8025`.
- Reset verification creates a short-lived single-use authorization; store only its digest. Successful password changes increment `users.token_version` to reject prior access JWTs.
- Keep SMTP mocked in automated tests. Apply Alembic migrations to the intended local PostgreSQL database only after checking that target is reachable.
- APIs: `/api/v1/auth/signup/send-otp`, `/signup/verify-otp`, `/register`, `/forgot-password`, `/verify-reset-otp`, and `/reset-password`.

Use AI assistance as a drafting and review aid; maintainers own the design, code, and release decisions.

1. Provide only the task context and synthetic examples needed. Never paste credentials, production documents, personal data, or unredacted security findings into prompts.
2. Ask for a small, scoped change and the assumptions, files, security implications, and validation steps to accompany it.
3. Review every generated diff for correctness, authorization boundaries, injection risks, secret exposure, dependency changes, and license compatibility.
4. Run the relevant automated checks and inspect their output. Do not claim a check passed unless it was executed.
5. Require human review for authentication, access control, cryptography, migrations, file handling, and deployment configuration.
6. Do not treat generated code or explanations as authoritative; consult primary documentation and record material design decisions.
7. Keep bootstrap passwords, JWT/OTP secrets, SMTP credentials, OTP values, and user registration data out of prompts, logs, screenshots, fixtures and frontend bundles. Use dummy credentials and mocked email delivery in tests.
8. Review migrations against the actual configured database before applying them. Auth, approval, role and status changes must be transactional and audit actor/target/action metadata.

Suggested prompt: “Make the smallest change that satisfies [requirement]. Preserve the permanent VaultTrace folder structure and existing `.env`/database configuration. Identify security assumptions, changed files, and exact checks to run. Do not add unrelated features or expose credentials/OTPs.”

---

# Commit 1: Foundation, authentication, registration approval, email OTP, and password reset

## Complete implementation prompt and scope

> Continue the existing VaultTrace project; do not recreate it, change its permanent folder structure, create duplicate applications, or start Commit 2. Preserve existing user data, PostgreSQL credentials, and the local `.env`. Initialize and maintain the Python 3.12/FastAPI and React/TypeScript/Vite applications with PostgreSQL, SQLAlchemy 2, Alembic, Pydantic 2, JWT authentication, Argon2 password hashing, Pytest, and Playwright with TypeScript. Keep business logic in services; keep versioned HTTP endpoints under `api/v1`, models under `models`, schemas under `schemas`, and settings in `config.py`.
>
> Implement Administrator, Owner, and Viewer roles; one-time environment-configured administrator bootstrap; registration, login, logout, JWT validation and protected APIs; verified signup applications requiring administrator review; administrator overview, user/application listing, approve/reject, role and status management; and actor/target/action audit records. Do not allow public users to set roles or bypass approval.
>
> Keep admin APIs under `/api/v1/admin`: `GET /dashboard`, `GET /users`, `GET /applications`, `GET /applications/{application_id}`, `POST /applications/{application_id}/approve`, `POST /applications/{application_id}/reject`, `PATCH /users/{user_id}/role`, and `PATCH /users/{user_id}/status`. Source all totals and listings from PostgreSQL. Approval requires verified email and Owner or Viewer assignment; rejection stores a reason; both record reviewer and timestamp and notify the applicant. Protect Administrator accounts from unauthorized role/status changes. Audit approval, rejection, role assignment/modification, activation, deactivation, and suspension.
>
> Implement purpose-scoped signup and password-reset OTPs in a dedicated PostgreSQL `email_verifications` table with a nullable user foreign key, keyed OTP digest, purpose, expiry, attempts, verification/use/delivery state, and timezone-aware timestamps. Generate six-digit codes with a cryptographic random source; enforce five-minute expiry, five attempts, a 60-second resend cooldown and configured send limits; invalidate prior codes; prevent replay; and make verification single-use and atomic. Send multipart plain-text/HTML messages through SMTP configured only by environment variables; support local Mailpit; never log or persist plaintext OTPs, passwords, or reset tokens.
>
> Signup must require verified email before creating an inactive PENDING user/application with no user-selected elevated role. Forgot-password responses must not reveal whether an address exists. Reset must require a verified reset OTP and a short-lived, single-use authorization, hash the new password with Argon2, invalidate reset challenges, and revoke existing JWT sessions where supported. Provide signup, OTP, login, forgot-password, reset-password, and role-aware dashboard interfaces with validation/loading/error feedback. Keep OTPs and SMTP secrets out of frontend persistence/code.
>
> Provide `POST /api/v1/auth/signup/send-otp`, `POST /api/v1/auth/signup/verify-otp`, and `POST /api/v1/auth/register`; and `POST /api/v1/auth/forgot-password`, `POST /api/v1/auth/verify-reset-otp`, and `POST /api/v1/auth/reset-password`. Signup collects full name, username, email, optional phone, password, and confirmation. Route users after login by their server-validated role: Administrator to `/admin/dashboard`, Owner to `/owner/dashboard`, Viewer to `/viewer/dashboard`.
>
> Add isolated-database backend tests with mocked SMTP; document the workflow, APIs, environment configuration, migration, setup, and AI-assisted development process. Preserve existing files and credentials; inspect the database before migrations and apply only additive migrations after confirming the configured local PostgreSQL target. Run backend tests and the frontend production build, report only checks actually executed, do not deploy, commit, or push automatically, and do not begin Commit 2.

## Features implemented in Commit 1

- FastAPI authentication and protected APIs; Administrator, Owner, and Viewer roles; Argon2 password hashes; JWT issue/validation/revocation and role checks.
- Environment-driven, one-time administrator bootstrap; pending registration applications; administrator dashboard, user/application management, approval/rejection, role/status changes, and audit records.
- `email_verifications` records with `SIGNUP` and `PASSWORD_RESET` purposes, UUID keys, nullable user foreign key, indexed lifecycle state, keyed OTP hashes, delivery state, expiry, attempt and resend limits, and replay protection.
- SMTP multipart OTP email delivery with environment configuration and local Mailpit support. Signup OTP verification is bound to one registration.
- Generic forgot-password response; short-lived, single-use reset authorization; Argon2 password update; invalidation of outstanding reset OTPs and existing access JWTs through `token_version`.
- React signup and OTP flow, login, role-aware routes, forgot/reset pages, OTP input/countdown, and password confirmation. Signup validation displays FastAPI field errors.

## Commit 1 file and module inventory

This inventory covers the project source/configuration paths; generated environments, caches, build output, local `.env`, and local database contents are excluded.

- Root: `.env.example`, `.gitignore`, `README.md`, `PROMPTS.md`, `THREATS.md`, `LICENSE`, `requirements.txt`, `docker-compose.yml`.
- CI/container: `.github/workflows/ci.yml`, `backend/Dockerfile`, `frontend/Dockerfile`.
- Backend migration/config: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/20261103_0001_auth_foundation.py`, `20261103_0002_registration_admin.py`, `20261103_0003_email_verifications.py`.
- Backend application: `backend/app/__init__.py`, `main.py`, `bootstrap_admin.py`, `seed_roles.py`; `api/__init__.py`, `api/dependencies.py`, `api/v1/__init__.py`, `api/v1/router.py`, `api/v1/admin.py`; `core/__init__.py`, `core/config.py`, `core/security.py`; `db/__init__.py`, `db/base.py`, `db/session.py`; `models/__init__.py`, `models/user.py`, `role.py`, `registration_application.py`, `otp_challenge.py`, `email_verification.py`, `revoked_token.py`, `audit_log.py`; `schemas/__init__.py`, `schemas/auth.py`, `admin.py`, `health.py`; `services/__init__.py`, `auth.py`, `admin.py`, `registrations.py`, `otp.py`, `email.py`, `email_verifications.py`, `health.py`; `utils/__init__.py`, `utils/identifiers.py`.
- Backend tests: `backend/tests/__init__.py`, `client.py`, `conftest.py`, `database.py`, `test_auth_api.py`, `test_email_verifications.py`, `test_security.py`.
- Frontend configuration: `frontend/package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.js`, `postcss.config.js`, `playwright.config.ts`, `index.html`.
- Frontend source: `frontend/src/App.tsx`, `main.tsx`, `styles.css`, `vite-env.d.ts`; `components/AdminLayout.tsx`, `OtpInput.tsx`, `OtpVerification.tsx`, `PasswordConfirmation.tsx`, `Placeholder.tsx`; `context/AppContext.tsx`; `hooks/useHealth.ts`; `pages/AdminApplicationsPage.tsx`, `AdminDashboardPage.tsx`, `AdminUsersPage.tsx`, `DashboardPage.tsx`, `ForgotPasswordPage.tsx`, `HomePage.tsx`, `LoginPage.tsx`, `ResetPasswordPage.tsx`, `SignupPage.tsx`; `services/api.ts`; `types/index.ts`; `utils/format.ts`.
- Frontend browser-test source: `frontend/e2e/smoke.spec.ts`.

## Dependencies and configuration

- Backend ranges are declared in `requirements.txt`: FastAPI, Uvicorn, SQLAlchemy 2.x, Psycopg 3, Alembic, Pydantic 2 and pydantic-settings, python-jose, pwdlib with Argon2, email-validator, pytest, HTTPX, and AnyIO.
- Frontend dependencies and scripts are in `frontend/package.json`: React 18, TypeScript 5, Vite 5, React Router 6, Axios, Tailwind CSS 3, Playwright, and type/build tooling. `npm run build` runs strict TypeScript checking and Vite production bundling.
- `.env.example` documents database/JWT/OTP/bootstrap placeholders, SMTP host/port/auth/sender/TLS, reset-authorization lifetime, and frontend API URL. The local `.env` is private and must not be copied into documentation or source.
- Alembic revision `20261103_0003` creates the OTP/reset-authorization tables and adds `users.token_version`; PostgreSQL reported this revision as current head, and both tables were inspected after migration. Docker Compose defines app and Mailpit services; PostgreSQL remains the existing local development database.

## Actual validation record

Executed during Commit 1 continuation (results refer to those commands/runs, not future runs):

- `PYTHONPATH=backend likitha/bin/python -m pytest backend/tests -q` — **17 passed** (latest backend run after the PostgreSQL row-lock fix).
- `cd frontend && PATH=/tmp/vaulttrace-node/bin:$PATH npm run build` — **passed** (TypeScript check and Vite production build).
- `PYTHONPATH=backend likitha/bin/python -m compileall -q backend/app backend/tests` — **passed**.
- `PYTHONPATH=backend likitha/bin/alembic -c backend/alembic.ini upgrade head --sql` — **passed** as offline migration SQL generation.
- `docker compose config --quiet` — **passed**.
- `pg_isready -h 127.0.0.1 -p 5432` — PostgreSQL reported accepting connections; `PYTHONPATH=backend likitha/bin/alembic -c backend/alembic.ini current` — revision `20261103_0003 (head)`.
- A read-only schema inspection confirmed `email_verifications`, `password_reset_authorizations`, and `users.token_version` exist.
- A rollback-only service-level signup OTP send/verify round-trip against the configured PostgreSQL database and local Mailpit passed with a synthetic recipient. A login check for a locally provisioned admin also passed. No real recipient mailbox or external SMTP provider was tested.
- `git diff --check` — **passed**.

## Known issues and pending verification

- Mailpit captures local email at `http://localhost:8025`; it does not deliver to real inboxes. Configure a legitimate SMTP provider and verify a real recipient mailbox before relying on external email.
- The live PostgreSQL/Mailpit check exercised the service path with a synthetic address and rolled back database writes. A full browser-driven signup → admin approval → login run has not been recorded as verified; Playwright E2E was not run.
- The local database contains development administrator accounts, including one created for manual feature checks. Rotate any weak development password before using a shared or production environment. No admin email/password values are recorded here.
- Production deployment, production SMTP, backups, monitoring, and production security review remain pending. Commit 2 document-storage/sharing features are intentionally out of scope.
