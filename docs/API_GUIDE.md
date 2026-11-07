# API guide

The API base path is `/api/v1`. Request and response schemas are defined in `backend/app/schemas/`; routes are registered in `backend/app/api/v1/router.py`, `admin.py`, and `documents.py`. The running FastAPI app exposes Swagger UI at `/docs` and OpenAPI JSON at `/openapi.json`.

For example, the source-backed current-user endpoint delegates authentication to the shared dependency:

```python
@api_router.get("/users/me", response_model=UserResponse, tags=["users"])
def read_current_user(user: User = Depends(get_current_user)) -> UserResponse:
    return public_user(user)
```

This excerpt is from `backend/app/api/v1/router.py`; `get_current_user` validates the bearer token and loads the current active account. The registered URL is `GET /api/v1/users/me`.

Set a local base URL for examples:

```bash
export API_BASE='http://localhost:8000/api/v1'
```

Use HTTPS and the deployed backend host outside local development. Do not put passwords or tokens into shell history; replace placeholder values with a secure local input method.

## Authentication and registration

### Request a signup OTP

```http
POST /api/v1/auth/signup/send-otp
Content-Type: application/json
```

```json
{"email":"applicant@example.test"}
```

Response: `202 Accepted`, with a generic message. A successful response does not disclose the OTP. Requests can return `429` for cooldown/rate limits or `503` when delivery/database services fail.

### Verify signup OTP

```http
POST /api/v1/auth/signup/verify-otp
Content-Type: application/json
```

```json
{"email":"applicant@example.test","otp":"123456"}
```

Response:

```json
{"message":"Email verified. You may submit your registration."}
```

The numeric code above is an example placeholder, not a working OTP.

### Submit a registration application

```http
POST /api/v1/auth/register
Content-Type: application/json
```

```json
{
  "full_name":"Example Applicant",
  "username":"example-applicant",
  "email":"applicant@example.test",
  "phone_number":"+10000000000",
  "password":"REPLACE_WITH_A_SECURE_PASSWORD",
  "confirm_password":"REPLACE_WITH_A_SECURE_PASSWORD"
}
```

Password fields are 12–128 characters and must match. The client cannot choose a role. New accounts are inactive and pending administrator review.

### Login and current user

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{"email":"user@example.test","password":"REPLACE_WITH_A_SECURE_PASSWORD"}
```

Successful response shape:

```json
{
  "access_token":"<short-lived-bearer-token>",
  "token_type":"bearer",
  "expires_at":"<UTC timestamp>",
  "user":{
    "id":1,
    "email":"user@example.test",
    "full_name":"Example User",
    "username":"example-user",
    "role":"Owner",
    "account_status":"ACTIVE"
  }
}
```

Protected requests send the token in the HTTP Authorization header:

```bash
curl --fail-with-body "$API_BASE/users/me" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

`GET /users/me` returns the authenticated profile. `POST /auth/logout` requires the same bearer header and returns `204 No Content`; the token's `jti` is then rejected.

### Password reset

1. `POST /auth/forgot-password` with `{"email":"user@example.test"}`. The response is generic.
2. `POST /auth/verify-reset-otp` with `{"email":"user@example.test","otp":"123456"}`. The response contains `authorization_token` and `expires_in_seconds` only when valid.
3. `POST /auth/reset-password` with `{"authorization_token":"<reset-authorization>","password":"REPLACE_WITH_A_NEW_SECURE_PASSWORD","confirm_password":"REPLACE_WITH_A_NEW_SECURE_PASSWORD"}`.

The reset authorization is short-lived and single-use. Resetting increments the user's token version and invalidates existing access tokens.

## Documents

Every document endpoint requires a bearer token. File bytes are uploaded as multipart form data.

### Upload

```bash
curl --fail-with-body "$API_BASE/documents/upload" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F 'file=@./example.pdf;type=application/pdf' \
  -F 'document_name=Example document' \
  -F 'category=Contracts' \
  -F 'description=Optional description' \
  -F 'visibility=PRIVATE'
```

Only an Owner account can upload. The server validates size, extension, MIME, and file signature. Supported formats and the configured size limit are described in `.env.example` and [Security](SECURITY.md).

### List, search, preview and download

- `GET /documents/` — caller's owned documents, with search/category/date/pagination/sort filters.
- `GET /documents/search` — authorized owned and shared document search.
- `GET /documents/{document_id}` — authorized metadata.
- `GET /documents/{document_id}/preview` — inline PDF, PNG, JPEG, or TXT only.
- `GET /documents/{document_id}/download` — authorized attachment download.
- `GET /documents/{document_id}/versions` and `GET /documents/{document_id}/versions/{version_id}/download` — version metadata and historical download.
- `GET /documents/shared-with-me`, `/documents/shared-by-me`, `/documents/deleted`, `/documents/categories` — sharing, deletion, and category views.

Download example:

```bash
curl --fail-with-body "$API_BASE/documents/$DOCUMENT_ID/download" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  --output downloaded-document
```

### Share a document

```http
POST /api/v1/documents/{document_id}/permissions
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "recipient_email":"colleague@example.test",
  "permission_level":"READ",
  "expires_at":"2030-01-01T00:00:00Z"
}
```

Exactly one of `recipient_email` or `recipient_user_id` is required. `permission_level` accepts `READ` or `EDIT` (legacy `VIEWER`/`EDITOR` labels remain accepted). Expiration is optional and must be in the future. Recipients must be active, verified, and in the same organization as the owner. Grant management endpoints include:

- `GET /documents/{document_id}/eligible-users`
- `GET /documents/{document_id}/permissions`
- `PATCH /documents/{document_id}/permissions/{permission_id}`
- `DELETE /documents/{document_id}/permissions/{permission_id}`

Editors can update metadata and create versions. Only the actual owner can manage grants, delete/restore, or inspect per-document activity. `POST /documents/{document_id}/restore` restores a soft-deleted document; `DELETE /documents/{document_id}` soft-deletes it.

## Administration

All `/admin/*` endpoints require the Administrator role.

| Method and path | Purpose |
|---|---|
| `GET /admin/dashboard` | Dashboard counts. |
| `GET /admin/users` | Paginated users. |
| `GET /admin/applications`, `GET /admin/applications/{id}` | Review queue and application details. |
| `POST /admin/applications/{id}/approve` | Approve with `{"role":"Owner"}` or `{"role":"Viewer"}`. |
| `POST /admin/applications/{id}/reject` | Reject with a bounded reason. |
| `PATCH /admin/users/{id}/role` | Change an approved non-admin role. |
| `PATCH /admin/users/{id}/status` | Activate, deactivate, or suspend a non-admin. |
| `GET /admin/organizations`, `POST /admin/organizations` | Manage organizations. |
| `PATCH /admin/users/{id}/organization` | Assign or unassign a user. |
| `GET /admin/audit-logs`, `/summary`, `/{event_id}`, `/export.csv` | Filter, summarize, inspect, and export audit data. |
| `GET /admin/documents`, `/documents/audit`, `/documents/permissions` | Inspect document metadata and collaboration events. |
| `DELETE /admin/documents/permissions/{permission_id}` | Revoke a grant without granting file access. |

The first Administrator is created through the explicit bootstrap script, not public signup. See [Deployment](DEPLOYMENT.md#administrator-bootstrap).

## Legacy OTP routes

`POST /auth/otp/request`, `/auth/otp/resend`, and `/auth/otp/verify` remain mounted and use the earlier `otp_challenges` table. Current frontend signup and password-reset flows use the purpose-specific endpoints described above.

## Errors and OpenAPI

Common responses include `400` for invalid/expired OTP or reset tokens, `401` for invalid credentials or bearer token, `403` for insufficient permission, `404` for concealed/missing documents, `409` for state conflicts, `422` for schema/file validation, `429` for OTP limits, and `503`/`502` for database or storage failures. Exact response schemas are available from the running OpenAPI document at `/openapi.json`.
