"""Private local and Supabase storage providers behind one interface."""

import errno
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote, urlparse

import httpx

from app.core.config import settings
from app.services.document_validation import validate_upload


class StorageConfigurationError(Exception):
    """Raised when private Supabase Storage is absent or misconfigured."""


class StorageOperationError(Exception):
    """Raised when Supabase Storage cannot complete a backend operation."""


class StorageService(Protocol):
    """Common storage contract used by document services."""

    provider_name: str
    def upload_file(self, storage_key: str, content: bytes, mime_type: str, bucket: str | None = None) -> None: ...
    def download_file(self, storage_key: str, bucket: str | None = None) -> bytes: ...
    def delete_file(self, storage_key: str, bucket: str | None = None) -> None: ...
    def file_exists(self, storage_key: str, bucket: str | None = None) -> bool: ...
    def close(self) -> None: ...


def _validated_key_parts(storage_key: str) -> tuple[str, ...]:
    """Parse a relative POSIX storage key and reject traversal or absolute paths."""
    if not storage_key or storage_key.startswith("/") or "\\" in storage_key or "\x00" in storage_key:
        raise StorageConfigurationError("Storage object key is invalid.")
    raw_parts = storage_key.split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise StorageConfigurationError("Storage object key is invalid.")
    return tuple(PurePosixPath(storage_key).parts)


class LocalStorageProvider:
    """Private filesystem storage outside all frontend static/public directories."""

    provider_name = "local"
    local_bucket = "local-private-storage"

    def __init__(self, storage_path: str | Path, max_upload_bytes: int | None = None) -> None:
        """Initialize the private root, creating it only when an operation needs it."""
        self.storage_path = Path(storage_path).expanduser()
        self.max_upload_bytes = settings.document_max_upload_bytes if max_upload_bytes is None else max_upload_bytes

    @classmethod
    def from_settings(cls) -> "LocalStorageProvider":
        """Build the local provider from environment-based backend settings."""
        return cls(settings.local_storage_path, settings.document_max_upload_bytes)

    def _root(self, *, create: bool) -> Path:
        configured = self.storage_path.absolute()
        root = configured.resolve(strict=False)
        project_root = Path(__file__).resolve().parents[3]
        public_roots = (
            project_root / "frontend" / "public",
            project_root / "frontend" / "static",
            project_root / "frontend" / "dist",
            project_root / "backend" / "app" / "static",
        )
        if any(root == public.resolve(strict=False) or public.resolve(strict=False) in root.parents for public in public_roots):
            raise StorageConfigurationError("Local storage cannot be inside a public or static directory.")
        if create:
            try:
                root.mkdir(mode=0o700, parents=True, exist_ok=True)
                if root.is_symlink() or not root.is_dir():
                    raise StorageConfigurationError("Local storage root must be a private directory.")
                if os.name == "posix":
                    root.chmod(0o700)
            except OSError as exc:
                raise StorageOperationError("Local storage directory is unavailable.") from exc
        return root

    def _target(self, storage_key: str, *, create_parents: bool) -> Path:
        """Resolve a key beneath the private root and reject symlinked parents."""
        parts = _validated_key_parts(storage_key)
        root = self._root(create=create_parents)
        current = root
        for part in parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise StorageConfigurationError("Local storage key traverses a symbolic link.")
            if create_parents:
                try:
                    current.mkdir(mode=0o700, exist_ok=True)
                except OSError as exc:
                    raise StorageOperationError("Local storage directory is unavailable.") from exc
            if current.exists() and not current.is_dir():
                raise StorageConfigurationError("Local storage key contains a non-directory path component.")
            if not current.resolve(strict=False).is_relative_to(root):
                raise StorageConfigurationError("Local storage key escapes its private directory.")
        target = current / parts[-1]
        if target.is_symlink() or not target.resolve(strict=False).is_relative_to(root):
            raise StorageConfigurationError("Local storage key escapes its private directory.")
        return target

    @staticmethod
    def _raise_local_error(exc: OSError) -> None:
        if exc.errno == errno.ELOOP:
            raise StorageConfigurationError("Local storage does not follow symbolic links.") from exc
        raise StorageOperationError("Local storage operation failed.") from exc

    def upload_file(self, storage_key: str, content: bytes, mime_type: str, bucket: str | None = None) -> None:
        """Create a new private object exclusively, refusing oversize or empty bytes."""
        del bucket
        if not content or len(content) > self.max_upload_bytes:
            raise StorageConfigurationError("File is empty or exceeds the configured upload limit.")
        _validated_key_parts(storage_key)
        validate_upload(PurePosixPath(storage_key).name, mime_type, content)
        target = self._target(storage_key, create_parents=True)
        try:
            with target.open("xb") as output:
                output.write(content)
            if os.name == "posix":
                target.chmod(0o600)
        except FileExistsError as exc:
            raise StorageOperationError("A file already exists for this storage key.") from exc
        except OSError as exc:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            self._raise_local_error(exc)

    def download_file(self, storage_key: str, bucket: str | None = None) -> bytes:
        """Read a regular file from the private root without following symlinks."""
        del bucket
        target = self._target(storage_key, create_parents=False)
        try:
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise StorageConfigurationError("Local storage object is not a regular file.")
            descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as source:
                return source.read()
        except FileNotFoundError as exc:
            raise StorageOperationError("Local storage object was not found.") from exc
        except OSError as exc:
            self._raise_local_error(exc)

    def delete_file(self, storage_key: str, bucket: str | None = None) -> None:
        """Remove an object from the private root without following symlinks."""
        del bucket
        target = self._target(storage_key, create_parents=False)
        try:
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise StorageConfigurationError("Local storage object is not a regular file.")
            target.unlink()
        except FileNotFoundError as exc:
            raise StorageOperationError("Local storage object was not found.") from exc
        except OSError as exc:
            self._raise_local_error(exc)

    def file_exists(self, storage_key: str, bucket: str | None = None) -> bool:
        """Check for a regular object without following a symlink."""
        del bucket
        target = self._target(storage_key, create_parents=False)
        try:
            return stat.S_ISREG(target.lstat().st_mode)
        except FileNotFoundError:
            return False
        except OSError as exc:
            self._raise_local_error(exc)

    def close(self) -> None:
        """No persistent connection is held by the filesystem provider."""
        return None


class SupabaseStorageProvider:
    """Supabase REST client that refuses missing or public document buckets."""

    provider_name = "supabase"

    def __init__(
        self,
        project_url: str | None,
        service_role_key: str | None,
        bucket: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Validate backend-only credentials without contacting the provider."""
        if not project_url or not service_role_key:
            raise StorageConfigurationError(
                "Supabase Storage is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the backend environment."
            )
        parsed = urlparse(project_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        if parsed.scheme != "https" and not local_http:
            raise StorageConfigurationError("SUPABASE_URL must use HTTPS, except for localhost development.")
        if not parsed.netloc or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", bucket):
            raise StorageConfigurationError("Supabase project URL or storage bucket name is invalid.")
        self.project_url = project_url.rstrip("/")
        self.bucket = bucket
        self._client = httpx.Client(
            base_url=f"{self.project_url}/storage/v1",
            headers={"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"},
            timeout=httpx.Timeout(30.0, connect=5.0),
            follow_redirects=False,
            transport=transport,
        )

    @classmethod
    def from_settings(cls) -> "SupabaseStorageProvider":
        """Build an adapter from server-side settings; never called by the frontend."""
        key = settings.supabase_service_role_key
        return cls(
            project_url=settings.supabase_url,
            service_role_key=key.get_secret_value() if key else None,
            bucket=settings.supabase_storage_bucket,
        )

    def close(self) -> None:
        """Release the per-request HTTP connection pool."""
        self._client.close()

    def _request(self, method: str, path: str, *, expected: set[int], **kwargs: object) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise StorageOperationError("Supabase Storage is unavailable.") from exc
        if response.status_code not in expected:
            raise StorageOperationError(f"Supabase Storage request failed with status {response.status_code}.")
        return response

    def _safe_key(self, storage_key: str, bucket: str | None) -> tuple[str, str]:
        """Reject traversal and bucket changes before constructing a provider URL."""
        selected_bucket = bucket or self.bucket
        _validated_key_parts(storage_key)
        if selected_bucket != self.bucket:
            raise StorageConfigurationError("Storage bucket or object key is invalid.")
        return quote(selected_bucket, safe=""), quote(storage_key, safe="/")

    def _assert_private_bucket(self) -> None:
        """Fail closed if the configured bucket is missing or public."""
        bucket_path = quote(self.bucket, safe="")
        response = self._request("GET", f"/bucket/{bucket_path}", expected={200, 404})
        if response.status_code == 404:
            raise StorageConfigurationError(
                f"Supabase bucket '{self.bucket}' was not found. Create it as a private bucket in the Supabase Dashboard."
            )
        try:
            details = response.json()
        except ValueError as exc:
            raise StorageConfigurationError("Supabase returned invalid bucket configuration.") from exc
        if not isinstance(details, dict) or details.get("public") is not False:
            raise StorageConfigurationError("The configured document bucket must be private.")

    def upload_file(self, storage_key: str, content: bytes, mime_type: str, bucket: str | None = None) -> None:
        """Upload bytes to the configured private bucket without overwriting."""
        bucket_path, object_path = self._safe_key(storage_key, bucket)
        validate_upload(PurePosixPath(storage_key).name, mime_type, content)
        self._assert_private_bucket()
        self._request(
            "POST",
            f"/object/{bucket_path}/{object_path}",
            expected={200, 201},
            content=content,
            headers={"Content-Type": mime_type, "x-upsert": "false"},
        )

    def download_file(self, storage_key: str, bucket: str | None = None) -> bytes:
        """Download object bytes through the authorized backend."""
        bucket_path, object_path = self._safe_key(storage_key, bucket)
        self._assert_private_bucket()
        return self._request("GET", f"/object/{bucket_path}/{object_path}", expected={200}).content

    def delete_file(self, storage_key: str, bucket: str | None = None) -> None:
        """Delete an object by exact key from the configured private bucket."""
        bucket_path, _object_path = self._safe_key(storage_key, bucket)
        self._assert_private_bucket()
        self._request("DELETE", f"/object/{bucket_path}", expected={200}, json={"prefixes": [storage_key]})

    def file_exists(self, storage_key: str, bucket: str | None = None) -> bool:
        """Check object metadata without downloading the file contents."""
        bucket_path, object_path = self._safe_key(storage_key, bucket)
        self._assert_private_bucket()
        response = self._request("GET", f"/object/info/{bucket_path}/{object_path}", expected={200, 404})
        return response.status_code == 200

    def generate_signed_url(self, storage_key: str, expires_in: int = 60, bucket: str | None = None) -> str:
        """Create an ephemeral URL for exceptional integrations; never persist it."""
        if not 1 <= expires_in <= 300:
            raise ValueError("Signed URL lifetime must be between 1 and 300 seconds.")
        bucket_path, object_path = self._safe_key(storage_key, bucket)
        self._assert_private_bucket()
        response = self._request(
            "POST",
            f"/object/sign/{bucket_path}/{object_path}",
            expected={200},
            json={"expiresIn": expires_in},
        )
        try:
            signed_path = response.json()["signedURL"]
        except (ValueError, KeyError, TypeError) as exc:
            raise StorageOperationError("Supabase did not return a signed URL.") from exc
        if not isinstance(signed_path, str):
            raise StorageOperationError("Supabase returned an invalid signed URL.")
        if signed_path.startswith("https://"):
            return signed_path
        return f"{self.project_url}/storage/v1{signed_path if signed_path.startswith('/') else '/' + signed_path}"


# Backwards compatibility for code/tests that imported the original adapter name.
SupabaseStorage = SupabaseStorageProvider


def create_storage_provider(provider_name: str | None = None) -> StorageService:
    """Construct exactly the requested provider; never fall back between providers."""
    selected = provider_name or settings.storage_provider
    if selected == "local":
        return LocalStorageProvider.from_settings()
    if selected == "supabase":
        return SupabaseStorageProvider.from_settings()
    raise StorageConfigurationError("STORAGE_PROVIDER must be either 'local' or 'supabase'.")
