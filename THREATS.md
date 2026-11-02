# VaultTrace threat model (initial template)

## Scope and assets

- Documents, metadata, identities, credentials, access policies, audit events, and signing/configuration secrets.
- API, web client, database, object-storage integration (not yet implemented), CI, and deployment environment.

## Trust boundaries

Record boundaries between browser, API, database, external identity providers, storage, operators, and CI. Treat all client input and uploaded content as untrusted.

## Threats to assess

- Authentication attacks: credential stuffing, weak session/token handling, token theft, and account enumeration.
- Authorization failures: cross-tenant access, insecure direct object references, privilege escalation, and stale permissions.
- Document risks: malicious uploads, malware, content-type confusion, path traversal, leakage through logs, and unsafe previews.
- Infrastructure risks: exposed secrets, database/network exposure, vulnerable dependencies, backup leakage, and denial of service.
- Supply-chain risks: compromised packages, CI credentials, and unreviewed AI-generated changes.

## Initial controls to design and verify

- Argon2 password hashing, short-lived JWTs with validated issuer/audience/algorithm, and rotation/revocation strategy.
- Deny-by-default authorization at service boundaries; tenant-scoped queries and auditable access decisions.
- File size/type limits, isolated scanning and storage, encryption in transit/at rest, and safe download headers.
- Secret management, least-privilege service identities, dependency review, rate limits, secure headers, and tested restore procedures.

## Open questions / review record

- Define tenant model, identity lifecycle, retention, data residency, encryption/key ownership, upload limits, and incident response.
- For each release, record threat, affected asset, likelihood/impact, owner, mitigation, and verification evidence.
- This template is not a completed security assessment. Review it before handling real documents or production data.
