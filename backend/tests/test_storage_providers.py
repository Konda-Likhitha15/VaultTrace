"""Provider contract, filesystem safety, selection, and mocked Supabase tests."""

import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.core.config import Settings
from app.services.document_validation import DocumentValidationError
from app.services.storage import (
    LocalStorageProvider,
    StorageConfigurationError,
    StorageOperationError,
    SupabaseStorageProvider,
    create_storage_provider,
)


def test_local_provider_upload_download_exists_delete_and_private_permissions(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path / "private_storage", max_upload_bytes=1024)
    key = f"users/23/{uuid4()}.txt"
    content = b"private synthetic file"

    provider.upload_file(key, content, "text/plain")
    stored = tmp_path / "private_storage" / key
    assert provider.file_exists(key)
    assert provider.download_file(key) == content
    if os.name == "posix":
        assert stored.stat().st_mode & 0o777 == 0o600
        assert (tmp_path / "private_storage").stat().st_mode & 0o777 == 0o700
    provider.delete_file(key)
    assert not provider.file_exists(key)
    provider.close()


@pytest.mark.parametrize("invalid_key", ["../outside.txt", "/tmp/outside.txt", "users/../secret", r"users\1\secret.txt", ""])
def test_local_provider_rejects_invalid_paths(tmp_path: Path, invalid_key: str) -> None:
    provider = LocalStorageProvider(tmp_path / "private_storage")
    with pytest.raises(StorageConfigurationError):
        provider.upload_file(invalid_key, b"file", "text/plain")


def test_local_provider_rejects_symlinked_parent_and_public_roots(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path / "private_storage")
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "private_storage"
    root.mkdir()
    (root / "users").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StorageConfigurationError):
        provider.upload_file(f"users/{uuid4()}/item.txt", b"content", "text/plain")

    repo_public = Path(__file__).resolve().parents[2] / "frontend" / "public" / "forbidden"
    with pytest.raises(StorageConfigurationError, match="public or static"):
        LocalStorageProvider(repo_public).upload_file(f"users/1/{uuid4()}.txt", b"x", "text/plain")
    assert list(outside.iterdir()) == []


def test_local_provider_enforces_size_and_storage_failures(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path / "private_storage", max_upload_bytes=3)
    with pytest.raises(StorageConfigurationError, match="upload limit"):
        provider.upload_file(f"users/1/{uuid4()}.txt", b"large", "text/plain")
    with pytest.raises(StorageConfigurationError):
        provider.upload_file(f"users/1/{uuid4()}.txt", b"", "text/plain")
    with pytest.raises(StorageOperationError):
        provider.download_file(f"users/1/{uuid4()}.txt")


def test_both_providers_reject_content_mime_mismatch_before_storage(tmp_path: Path) -> None:
    local = LocalStorageProvider(tmp_path / "private_storage")
    invalid_key = f"users/1/{uuid4()}.pdf"
    with pytest.raises(DocumentValidationError):
        local.upload_file(invalid_key, b"not really a PDF", "application/pdf")
    assert not (tmp_path / "private_storage").exists()

    def no_request(_request: httpx.Request) -> httpx.Response:
        pytest.fail("Supabase must validate file content before any network call.")

    supabase = SupabaseStorageProvider(
        "https://unit-test.supabase.co", "test-only-service-role-key", "vaulttrace-documents",
        transport=httpx.MockTransport(no_request),
    )
    with pytest.raises(DocumentValidationError):
        supabase.upload_file(invalid_key, b"not really a PDF", "application/pdf")
    supabase.close()


def test_provider_selection_is_explicit_and_never_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "storage_provider", "local")
    monkeypatch.setattr(settings, "local_storage_path", tmp_path / "configured-private")
    selected = create_storage_provider()
    assert isinstance(selected, LocalStorageProvider)
    assert selected.provider_name == "local"

    monkeypatch.setattr(settings, "storage_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_service_role_key", None)
    with pytest.raises(StorageConfigurationError, match="SUPABASE_URL"):
        create_storage_provider()


def test_production_defaults_to_supabase_without_explicit_provider() -> None:
    production_settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused:unused@localhost/vaulttrace",
        jwt_secret_key="test-only-secret-value-that-is-long-enough",
        app_env="production",
    )
    assert production_settings.storage_provider == "supabase"


def test_production_rejects_local_storage_provider() -> None:
    with pytest.raises(ValidationError, match="STORAGE_PROVIDER must be 'supabase'"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://unused:unused@localhost/vaulttrace",
            jwt_secret_key="test-only-secret-value-that-is-long-enough",
            app_env="production",
            storage_provider="local",
        )


def test_supabase_provider_upload_download_exists_delete_with_mocked_http() -> None:
    objects: dict[str, bytes] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bucket/vaulttrace-documents"):
            return httpx.Response(200, json={"id": "vaulttrace-documents", "public": False})
        if request.method == "POST" and "/object/vaulttrace-documents/" in request.url.path:
            objects[request.url.path.rsplit("/", 1)[-1]] = request.content
            return httpx.Response(200, json={"Key": request.url.path})
        if request.method == "GET" and "/object/info/" in request.url.path:
            return httpx.Response(200, json={"name": request.url.path.rsplit("/", 1)[-1]})
        if request.method == "GET" and "/object/vaulttrace-documents/" in request.url.path:
            key = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, content=objects[key])
        if request.method == "DELETE" and request.url.path.endswith("/object/vaulttrace-documents"):
            key = request.read().decode()
            import json

            object_name = json.loads(key)["prefixes"][0].rsplit("/", 1)[-1]
            objects.pop(object_name, None)
            return httpx.Response(200, json={"message": "deleted"})
        return httpx.Response(404)

    provider = SupabaseStorageProvider(
        "https://unit-test.supabase.co",
        "test-only-service-role-key",
        "vaulttrace-documents",
        transport=httpx.MockTransport(respond),
    )
    key = f"users/23/{uuid4()}.txt"
    content = b"mocked provider content"
    provider.upload_file(key, content, "text/plain")
    assert provider.file_exists(key)
    assert provider.download_file(key) == content
    provider.delete_file(key)
    assert not objects
    provider.close()


@pytest.mark.parametrize("invalid_key", ["../outside.txt", "/root/file", r"users\2\file", ""])
def test_supabase_provider_rejects_invalid_keys_before_network(invalid_key: str) -> None:
    def should_not_be_called(_request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid storage keys must be rejected before making a provider request.")

    provider = SupabaseStorageProvider(
        "https://unit-test.supabase.co", "test-only-service-role-key", "vaulttrace-documents",
        transport=httpx.MockTransport(should_not_be_called),
    )
    with pytest.raises(StorageConfigurationError):
        provider.file_exists(invalid_key)
    provider.close()


def test_supabase_storage_failures_are_reported_without_fallback() -> None:
    def unavailable(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = SupabaseStorageProvider(
        "https://unit-test.supabase.co", "test-only-service-role-key", "vaulttrace-documents",
        transport=httpx.MockTransport(unavailable),
    )
    with pytest.raises(StorageOperationError):
        provider.upload_file(f"users/1/{uuid4()}.txt", b"content", "text/plain")
    provider.close()
