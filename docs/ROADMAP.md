# Roadmap and known limitations

This roadmap is based on source present in this repository. Items marked “implemented” do not establish that production configuration is correct or that controls have undergone an independent assessment.

## Current capability snapshot

| Capability | State | Evidence / notes |
|---|---|---|
| Verified signup and application review | Implemented | Purpose-specific OTP, pending state, Administrator approval. |
| Password login/logout and reset | Implemented | Argon2, JWT expiry/revocation/version checks, one-time reset authorization. |
| Role and account management | Implemented | Administrator-only role/status endpoints for non-admin users. |
| Organizations | Implemented | Administrator assignment; existing users remain unassigned unless assigned. |
| Private document storage | Implemented | Local and Supabase providers; production mode refuses configured local storage. |
| Document validation and access checks | Implemented | Type/size/signature validation and server-side owner/grant checks. |
| Versions and recoverable deletion | Implemented | Version metadata and historical objects; soft-delete/restore. |
| Sharing | Implemented | Same-organization registered users, READ/EDIT, expiry, revocation. |
| Audit trail | Implemented | Application events and admin/document views; not immutable against DB operators. |
| Email | Partially implemented | SMTP/Mailpit and Gmail API; synchronous send with no durable queue/retry. |
| Search | Partially implemented | Metadata filters and pagination; no OCR or document-body indexing. |
| Production deployment | Partially documented | Dockerfiles exist; no Render manifest; frontend Docker image is development mode. |
| MFA, malware scanning, notification queue | Not implemented | Recommended below. |

## Known limitations

- No Render configuration file is present; live service settings were not inspected.
- The frontend Docker image runs Vite's development server. Use a Vite production build served as a static site for production.
- The backend Docker command hardcodes port 8000; verify the hosting platform port or configure it to match.
- `docker-compose.yml` does not include PostgreSQL and uses host networking for the backend.
- `/health` is a static liveness response and does not test database, storage, or email readiness.
- Login has no application-level rate limiter or lockout. OTP cooldown/hourly limits are per email, without visible IP/global controls.
- No MFA, malicious-file scanner, storage quota, durable email job queue, retention/purge schedule, or restore automation is present.
- Document contents are read into process memory by storage adapters before response streaming; increase limits only with resource/concurrency controls.
- Database and object-storage updates are not one atomic transaction. The code attempts cleanup after metadata failures, but cleanup failure can leave an orphan object.
- No backend dependency lockfile or automated dependency audit appears in the repository. The current GitHub Actions workflow does not run pytest or Playwright.
- Audit records are normal database rows and are not tamper-evident against privileged database operators.
- Migration `20261104_0005` assigns existing document rows the `supabase` provider label; confirm existing object location when upgrading a database with prior documents.
- The repository does not define backup policies, encryption-at-rest settings, disaster recovery, production TLS, or live cloud security controls.

## Prioritized roadmap

| Priority / phase | Enhancement | Scope and dependencies |
|---|---|---|
| **P0 – Credential hygiene** | Revoke and rotate any disclosed OAuth/service credentials; define secret ownership and rotation. | Operations first; do not put credentials in client assets or logs. |
| **P1 – Production baseline** | Require production settings, use a production frontend build, honor the platform port, verify exact CORS/TLS/security headers, separate runtime/migration DB roles. | Deployment config and release process. |
| **P1 – Abuse controls** | Add distributed login/OTP/IP/global rate limits and alerts. | Shared limiter (for multi-instance deployments), generic auth responses, tests. |
| **P1 – CI/release safety** | Run backend tests and browser tests; add dependency, secret, SBOM, and container scanning; use reproducible locked installs. | CI workflow and lockfile policy. |
| **P1 – Data recovery** | Back up PostgreSQL and object storage; conduct restore drills and document migration rollback/recovery. | Provider configuration and recovery ownership. |
| **P2 – Stronger identity** | Add MFA/WebAuthn, recovery codes, admin step-up authentication, and session/device management. | Enrollment/recovery UX and security review. |
| **P2 – File safety** | Quarantine and malware scan files; add storage quotas, upload concurrency/request limits, and optional streaming. | Background job worker and storage state model. |
| **P2 – Audit operations** | Export security events to an immutable/independently controlled sink; alert on privileged changes; define retention and purge. | Monitoring, access policies, compliance/legal input. |
| **P2 – Reliable notifications** | Introduce transactional outbox/background workers, retry policy, dead-letter handling, and notification status. | Queue/broker and outbox table migration. |
| **P3 – Enterprise documents** | Add tags/custom metadata, OCR/full-text indexing, saved filters, policy-based retention, e-signature/workflow integrations. | Search/indexing and product requirements. |
| **P3 – Scale/performance** | Add DB query/index monitoring, load tests, object transfer optimization, caching only where measurements justify it. | Metrics baseline and target service levels. |

## Suggested implementation order

1. Contain exposed secrets and verify production host/database/storage settings.
2. Fix deployment and CI foundations before adding more product features.
3. Add rate limits and MFA, then test account recovery and cross-role authorization.
4. Add scanning, quotas, backups, retention, and consistency/reconciliation for storage.
5. Add durable notifications, external audit/monitoring, and enterprise search/workflows.

See [Security](SECURITY.md) for control-level recommendations and [Deployment](DEPLOYMENT.md) for the current repository deployment shape.
