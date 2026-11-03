"""Shared file validation used before any storage provider writes document bytes."""

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.core.config import settings


class DocumentValidationError(Exception):
    """Raised when uploaded bytes or their declared file attributes are invalid."""


@dataclass(frozen=True)
class ValidatedFile:
    """Validated file properties used to persist document metadata."""

    original_filename: str
    extension: str
    mime_type: str
    size: int
    checksum: str


MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _safe_original_filename(filename: str | None) -> str:
    """Keep only a display basename and remove path/control characters."""
    if not filename:
        raise DocumentValidationError("A filename is required.")
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(char for char in basename if ord(char) >= 32 and ord(char) != 127).strip()
    if not cleaned or cleaned in {".", ".."} or len(cleaned) > 255:
        raise DocumentValidationError("The filename is invalid or too long.")
    return cleaned


def _validate_signature(extension: str, content: bytes) -> str:
    """Detect supported formats from bytes rather than trusting browser MIME."""
    if extension == ".pdf" and content.startswith(b"%PDF-"):
        return MIME_BY_EXTENSION[extension]
    if extension == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        return MIME_BY_EXTENSION[extension]
    if extension in {".jpg", ".jpeg"} and content.startswith(b"\xff\xd8\xff"):
        return MIME_BY_EXTENSION[extension]
    if extension in {".txt", ".csv"}:
        if b"\x00" not in content:
            try:
                content.decode("utf-8-sig", errors="strict")
                return MIME_BY_EXTENSION[extension]
            except UnicodeDecodeError:
                pass
    if extension in {".docx", ".xlsx"} and content.startswith(b"PK\x03\x04"):
        required_entry = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if required_entry in archive.namelist():
                    return MIME_BY_EXTENSION[extension]
        except (OSError, zipfile.BadZipFile):
            pass
    raise DocumentValidationError("The file content does not match a supported document type.")


def validate_upload(filename: str | None, supplied_mime: str | None, content: bytes) -> ValidatedFile:
    """Validate upload size, extension, content signature, MIME, and checksum."""
    if not content:
        raise DocumentValidationError("Empty files cannot be uploaded.")
    if len(content) > settings.document_max_upload_bytes:
        raise DocumentValidationError(f"File exceeds the {settings.document_max_upload_bytes}-byte upload limit.")
    original_filename = _safe_original_filename(filename)
    extension = PurePosixPath(original_filename).suffix.lower()
    configured_extensions = {
        f".{item.strip().lower().lstrip('.')}"
        for item in settings.document_allowed_extensions.split(",")
        if item.strip()
    }
    if extension not in configured_extensions or extension not in MIME_BY_EXTENSION:
        raise DocumentValidationError("This file extension is not allowed.")
    actual_mime = _validate_signature(extension, content)
    supplied = (supplied_mime or "").split(";", 1)[0].strip().lower()
    if supplied != actual_mime:
        raise DocumentValidationError("The supplied MIME type does not match the detected file content.")
    return ValidatedFile(
        original_filename=original_filename,
        extension=extension,
        mime_type=actual_mime,
        size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
    )
