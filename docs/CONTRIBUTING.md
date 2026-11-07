# Contributing

Thank you for helping improve VaultTrace. Keep changes reviewable and align code, tests, and documentation with the behavior actually implemented.

## Before making a change

1. Read [Architecture](ARCHITECTURE.md), [Security](SECURITY.md), and [Database](DATABASE.md) for the affected area.
2. Check the current route/schema/model/service behavior before changing an API or data model.
3. Never include `.env`, `credentials.json`, `.gmail_token.json`, database URLs, access/refresh tokens, service-role keys, user files, or production data in commits, logs, screenshots, or examples.
4. For schema changes, create an Alembic migration and test it against an empty database and a representative prior schema/data snapshot. Do not modify historical migrations already used by deployed environments.

## Local checks

From the repository root, with local dependencies installed and a test database configured:

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
python -m compileall -q backend
```

Frontend build:

```bash
cd frontend
npm ci
npm run build
```

Optional browser suite:

```bash
npx playwright install chromium
npm run test:e2e
```

The current GitHub Actions workflow runs Python compilation and a frontend build only. Local test success does not mean those tests are required CI gates yet.

## Code expectations

- Put authorization decisions in backend dependencies/services; client route guards are only a user-interface aid.
- Keep document ownership, grant, expiry, organization, and account-state checks centralized and add negative tests for cross-user access.
- Use Pydantic schemas for input constraints and SQLAlchemy expressions for database queries.
- Never log passwords, OTPs, JWTs, reset authorizations, OAuth secrets, storage keys, file content, or connection URLs. Add a redaction test for new diagnostics.
- Keep storage private and use provider-specific object identifiers, not submitted paths.
- Preserve existing SMTP/Mailpit behavior when changing optional email transports.
- Keep examples free of production credentials and use reserved `.test` addresses and obvious placeholders.

## Pull requests

Include a concise summary, risk/compatibility notes, migration/backfill behavior if applicable, and the exact checks run. Update API and security documentation when public behavior changes. Do not deploy, commit credentials, or include real user data in fixtures.

## Reporting a security issue

Do not open a public issue containing secrets, exploit details, personal data, or production records. Contact the project maintainer privately and include only the minimum information needed to reproduce the issue safely.

## License

Contributions are subject to the repository [LICENSE](../LICENSE).
