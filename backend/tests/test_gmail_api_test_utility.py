"""Safety tests for the one-shot local Gmail API test utility."""

import base64
import json
from email import message_from_bytes
from email import policy

import pytest

from backend.scripts import test_gmail_api as utility


class FakeRefreshError(Exception):
    pass


class FakeCredentials:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.valid = False


class FakeResponse:
    payload = {"id": "mock-message-id"}

    def __init__(self, status_code: int):
        self.status_code = status_code
        self.closed = False

    def json(self):
        assert not self.closed
        return self.payload

    def close(self):
        self.closed = True


class FakeAuthorizedSession:
    status_code = 200
    response_payload = {"id": "mock-message-id"}
    calls = []

    def __init__(self, credentials, **kwargs):
        self.credentials = credentials
        self.kwargs = kwargs
        self.credentials.valid = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, *, json, timeout):
        type(self).calls.append((url, json, timeout))
        FakeResponse.payload = type(self).response_payload
        return FakeResponse(type(self).status_code)


def write_oauth_files(tmp_path):
    client_id = "mock-client-id"
    client_secret = "mock-client-secret"
    client = tmp_path / "credentials.json"
    token = tmp_path / ".gmail_token.json"
    client.write_text(json.dumps({"installed": {"client_id": client_id, "client_secret": client_secret}}))
    token.write_text(json.dumps({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": "mock-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": [utility.GMAIL_SEND_SCOPE],
    }))
    return client, token


def install_fake_auth(monkeypatch):
    FakeAuthorizedSession.calls = []
    FakeAuthorizedSession.status_code = 200
    FakeAuthorizedSession.response_payload = {"id": "mock-message-id"}
    monkeypatch.setattr(
        utility,
        "_google_auth_components",
        lambda: (FakeCredentials, FakeAuthorizedSession, FakeRefreshError),
    )


def test_one_shot_test_sends_one_mime_request_with_required_scope(tmp_path, monkeypatch: pytest.MonkeyPatch):
    client_file, token_file = write_oauth_files(tmp_path)
    install_fake_auth(monkeypatch)
    result = utility.send_one_test_email(
        "authorized@example.com",
        client_file=client_file,
        token_file=token_file,
    )
    assert result.oauth_authenticated and result.accepted
    assert result.http_status == 200 and result.message_id == "mock-message-id"
    assert len(FakeAuthorizedSession.calls) == 1
    url, payload, timeout = FakeAuthorizedSession.calls[0]
    assert url.endswith("users/authorized%40example.com/messages/send")
    assert timeout == (5, 20)
    padding = "=" * (-len(payload["raw"]) % 4)
    mime = message_from_bytes(base64.urlsafe_b64decode(payload["raw"] + padding), policy=policy.default)
    assert mime["From"] == "authorized@example.com"
    assert mime["To"] == "authorized@example.com"
    assert mime["Subject"] == utility.SUBJECT
    assert mime.get_body(preferencelist=("plain",)).get_content().strip() == utility.TEXT_BODY
    assert mime.get_body(preferencelist=("html",)).get_content().strip() == utility.HTML_BODY


def test_non_success_response_is_not_retried(tmp_path, monkeypatch: pytest.MonkeyPatch):
    client_file, token_file = write_oauth_files(tmp_path)
    install_fake_auth(monkeypatch)
    FakeAuthorizedSession.status_code = 429
    result = utility.send_one_test_email(
        "authorized@example.com",
        client_file=client_file,
        token_file=token_file,
    )
    assert result.oauth_authenticated and not result.accepted
    assert result.http_status == 429
    assert len(FakeAuthorizedSession.calls) == 1


def test_403_response_captures_safe_error_reason_before_closing(tmp_path, monkeypatch: pytest.MonkeyPatch):
    client_file, token_file = write_oauth_files(tmp_path)
    install_fake_auth(monkeypatch)
    FakeAuthorizedSession.status_code = 403
    FakeAuthorizedSession.response_payload = {
        "error": {
            "code": 403,
            "message": "Access denied for authorized@example.com using mock-refresh-token and mock-client-secret",
            "errors": [{"reason": "domainPolicy", "message": "private detail"}],
            "status": "PERMISSION_DENIED",
        }
    }

    result = utility.send_one_test_email(
        "authorized@example.com",
        client_file=client_file,
        token_file=token_file,
    )

    assert result.http_status == 403 and not result.accepted
    assert result.error_code == 403
    assert result.error_message == "Access denied for [REDACTED] using [REDACTED] and [REDACTED]"
    assert "mock-refresh-token" not in result.error_message
    assert "mock-client-secret" not in result.error_message
    assert result.error_reasons == ("domainPolicy",)
    assert result.error_status == "PERMISSION_DENIED"
    assert len(FakeAuthorizedSession.calls) == 1


def test_mismatched_or_missing_files_stop_before_auth_or_send(tmp_path, monkeypatch: pytest.MonkeyPatch):
    client_file, token_file = write_oauth_files(tmp_path)
    token_data = json.loads(token_file.read_text())
    token_data["client_id"] = "another-client"
    token_file.write_text(json.dumps(token_data))
    install_fake_auth(monkeypatch)
    with pytest.raises(utility.TestSetupError, match="do not match"):
        utility.send_one_test_email("authorized@example.com", client_file=client_file, token_file=token_file)
    assert FakeAuthorizedSession.calls == []
