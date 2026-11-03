# VaultTrace threat model

## Scope

This is an implementation-focused threat model for Commit 1 account/authentication, Commit 2 document storage, and Commit 3 document authorization/sharing. It is not a penetration test, formal risk assessment, or production security approval.

Assets include user identities and password hashes, JWT/OTP/reset secrets, document metadata, document bytes, storage keys/provider labels, PostgreSQL data, local storage contents, Supabase service-role credentials, SMTP credentials, and audit records.

## Trust boundaries

- Browser to FastAPI: all form fields, role values, filenames, MIME headers, filters, and document IDs are untrusted. Authorization is checked by FastAPI and the document service, not by React.
- FastAPI to PostgreSQL: SQLAlchemy stores account and document metadata. File bytes are not stored in PostgreSQL. Provider labels on each document determine which storage adapter is used for its bytes.
- FastAPI to local storage: the local provider writes below `LOCAL_STORAGE_PATH` (default `./private_storage`), applies private POSIX directory/file permissions, rejects traversal and symlinked path components, and never mounts this directory as a public HTTP static route. The host/container filesystem and its operators remain trusted.
- FastAPI to Supabase: only the backend holds the service-role key. The adapter checks that the configured bucket exists and is private. Service-role access is highly privileged and must remain protected.
- Application to SMTP: SMTP credentials are server-side settings. Local Mailpit captures mail and is not an external mailbox provider.
- Deployment and CI: environment variables, container mounts, migration permissions, dependencies, and backups are operator-controlled trust boundaries.
- Tenant membership: administrator-assigned `users.organization_id` defines the organization boundary. Email domains are not evidence of membership. Existing users remain unassigned until an administrator explicitly assigns them.

## Implemented controls

- Passwords are Argon2-hashed; signup and password-reset OTPs are purpose-scoped, hashed, short-lived, attempt-limited, cooldown-limited, and single-use. JWT authorization is enforced by FastAPI.
- Administrator role/status endpoints are protected by FastAPI's administrator role dependency. The service protects administrator accounts and self-targeting, verifies approved/email-verified state before activation, updates status/role transactionally, increments `token_version`, and records actor/target/action/value/result audit metadata. Authentication reads current active status from PostgreSQL and rejects stale token versions.
- Administrator row locks are scoped to the `users` table so PostgreSQL does not attempt to lock the nullable side of the joined role relationship. An additive user update timestamp migration preserves existing account rows.
- The `users.updated_at` column has a PostgreSQL `now()` server default so registration inserts that omit the timestamp satisfy the non-null constraint. Signup translates only unique-constraint failures into an email/username conflict; other integrity failures remain database errors.
- Upload validation checks configured extension, file content signature where supported, detected MIME, maximum size, empty content, sanitized display filename, and SHA-256 checksum before storage.
- Storage object keys use owner ID and a random document UUID, not the submitted filename. Local path handling rejects traversal and symlinks; private files are not exposed by a static route.
- Local and Supabase providers implement a shared interface. `STORAGE_PROVIDER` selects the destination for new uploads; unavailable selected providers fail clearly instead of falling back.
- Each document persists `storage_provider`. Reads/deletes select the provider recorded on that row, avoiding accidental provider switching. The additive `20261104_0005` migration marks pre-existing Commit 2 rows as Supabase-backed.
- Centralized document authorization checks current user status, ownership or a live/unexpired/unrevoked permission, and same-organization membership for shared access on each request. There is no authorization cache. READ/legacy VIEWER grants allow reading; EDIT/legacy EDITOR grants allow metadata and version edits. Legacy delegated OWNER grants are treated as EDIT and cannot manage sharing, delete, restore, or read owner-only audit. Only the actual document owner manages permissions, delete/restore, and activity. Visibility labels alone never grant access. Owner role is required to upload. Administrator status does not grant file-content access; admin APIs expose metadata/audit and can revoke a grant.
- Recipient search and grant creation are scoped to active, verified users assigned to the owner's organization. Grant creation rejects unregistered or unassigned recipients and cross-organization targets. Administrator assignment changes are audited; assigning or removing membership affects access at the next request.
- Document version metadata binds each retained object to its provider, bucket, key, checksum, uploader, and version number. Soft deletion hides content and revokes all grants; restore does not reinstate those grants.
- Document activity records include actor, document (when known), action, result, timestamp, bounded client metadata, and non-secret event details for upload, access denial/read/preview, metadata/version changes, permission changes, delete, and restore.
- Supabase object access goes through the backend. The code does not create public URLs; short-lived signed-URL support exists only on the provider and is not used by the current API.
- Document metadata is committed after file upload. On metadata failure, the service attempts to remove the uploaded object. On database delete failure, it attempts to restore the removed object.

## Threats and residual risks

| Threat | Current mitigation | Remaining risk / action |
| --- | --- | --- |
| Cross-user document access / guessed IDs | Queries limit results to owners or active explicit grants; metadata and bytes are authorized server-side and unauthorized IDs return 404. | Exercise grant expiry, revocation, role changes, and every route against live PostgreSQL and browser tests before release. |
| Cross-organization sharing / user discovery | Nullable organization membership is assigned by administrators; discovery and grant service check the current owner/recipient organization IDs. No domain-based inference. Existing users are unassigned. | PostgreSQL revision `20261104_0009` and live admin assignment flow are not applied/verified while the local database is unavailable. Decide org membership policy and assign users before testing sharing. |
| Permission escalation through legacy OWNER grants | Existing legacy OWNER values no longer grant permission administration or document ownership; at most EDIT content privileges remain. New grants accept only READ/EDIT (legacy VIEWER/EDITOR are mapped). | Review existing grants after migration and confirm users who held delegated OWNER should keep EDIT access under the stricter policy. |
| Malicious or mislabeled upload | Allowlist, size cap, signature checks where supported, MIME comparison, UUID storage keys. Preview is limited to PDF, PNG, JPEG, and text/plain, streamed with no-store/nosniff and a sandbox content security policy. | No malware scanning or content disarm/reconstruction. Treat downloads as untrusted and add scanning before production use. |
| Local path traversal or public exposure | Relative-key validation, root containment, symlink rejection, restrictive permissions, ignored storage directory, no static mount. | The local host/container administrator can read files. Protect and back up the mounted volume; use encrypted host disks and restrict service-account access. |
| Provider switch or partial migration | Provider label is stored per document; old rows are marked Supabase by migration; no automatic provider fallback. | Copy operations can fail mid-migration. Use maintenance mode, backups, checksum verification, resumable batches, and only update each row after verified copy. |
| Supabase service-role key compromise | Secret is backend-only and configured through environment settings. | The key can bypass normal bucket policies. Restrict access to deployment secrets, rotate after exposure, and monitor provider audit events. |
| Storage/database inconsistency | Compensating cleanup/restore attempts and document checksums. | Compensation can itself fail; reconcile orphaned objects and missing objects operationally. Add scheduled integrity/reconciliation tooling before production. |
| Sensitive information leakage | API schemas omit provider key/bucket; errors avoid credentials and contents; downloads/previews use no-store and nosniff; admin APIs expose metadata but not bytes. | Audit metadata and user-agent/IP fields still contain personal information; apply retention/access controls and review logs, crash reports, and backups. |
| Stale account or permission state | Account/token version and permission/org state are queried from PostgreSQL on authenticated document operations; grant revoke/expiry/organization mismatch applies on the next request. | Validate with live PostgreSQL after migration; requests already in flight cannot be revoked retroactively. |
| Admin operation unavailable or row-lock failure | Scoped `FOR UPDATE OF users`, transactional operations, safe HTTP 503 on update persistence errors, and clearer frontend errors. | Local PostgreSQL did not answer during this stage, so live migration/update verification remains pending. |
| Resource exhaustion | Configurable upload limit and paginated document list. | Rate limits and global concurrent upload quotas are not implemented. Enforce request/body limits and abuse controls at the proxy/API layer. |
| Database/provider migration mistakes | Additive Alembic revisions; provider and account timestamp migrations preserve IDs and metadata. | Migrations through `20261104_0009` must be applied and verified against the intended PostgreSQL database before release. Back up before migration. |

## Operational requirements

- Keep `.env` out of Git. Use a unique random `JWT_SECRET_KEY` and distinct `OTP_HASH_SECRET`; use a secret manager for deployment credentials.
- For local use, keep `STORAGE_PROVIDER=local` and protect/backup `private_storage`. For deployment, set `STORAGE_PROVIDER=supabase`, configure the backend-only service-role key, and confirm the bucket is private.
- Never switch providers expecting files to move. Follow the documented migration plan; preserve document UUIDs and all metadata, and update provider labels only after destination checksum verification.
- Apply migrations only after validating the database target. Monitor orphaned files and failed cleanup events without logging document contents or secrets.
- Enforce HTTPS, least-privilege host/container access, database backups, dependency updates, incident response, and tested restore procedures in deployment.

## Review record and open questions

- Confirm local-storage volume permissions and backup/encryption policies for each deployment host.
- Define malware scanning, retention/deletion policy, key rotation, audit retention, data residency, and recovery objectives before production use.
- Audit records are in the application database and are not cryptographically tamper-evident or exported to an independent append-only log. Define retention, privileged access, and alerting before production use.
- Migrations `20261104_0008` and `20261104_0009` and end-to-end share/revoke/version workflows still require verification against the intended local PostgreSQL instance; automated service tests use isolated SQLite and mocked storage.
- Revisit this model whenever storage providers, access rules, upload formats, or deployment boundaries change. Record owner, likelihood/impact, mitigation, and evidence for each production review.
