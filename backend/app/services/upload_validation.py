"""Shared validation for browser-controlled file uploads."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import HTTPException, status


DEFAULT_EXTENSIONS: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "text/plain": {".txt"},
    "text/csv": {".csv"},
    "application/vnd.ms-excel": {".csv"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "video/mp4": {".mp4"},
    "video/webm": {".webm"},
}


def safe_upload_name(
    filename: str | None,
    content_type: str,
    *,
    allowed_extensions: dict[str, set[str]] | None = None,
    fallback: str = "upload",
    max_length: int = 250,
) -> str:
    """Return a bounded basename and require its suffix to match the MIME type."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name:
        name = fallback
    if "\x00" in name or len(name) > max_length:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"File name must be {max_length} characters or fewer")

    extensions = (allowed_extensions or DEFAULT_EXTENSIONS).get(content_type, set())
    suffix = Path(name).suffix.casefold()
    if extensions and suffix not in extensions:
        expected = ", ".join(sorted(extensions))
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"File extension must match its type ({expected})",
        )
    return name


def validate_upload_signature(content: bytes, content_type: str) -> None:
    """Reject common disguised files before they enter storage."""
    if content.startswith((b"MZ", b"\x7fELF")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Executable content is not allowed")

    valid = True
    if content_type == "application/pdf":
        valid = content.startswith(b"%PDF-")
    elif content_type == "image/jpeg":
        valid = content.startswith(b"\xff\xd8\xff")
    elif content_type == "image/png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif content_type == "image/webp":
        valid = len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    elif content_type == "video/mp4":
        valid = len(content) >= 12 and content[4:8] == b"ftyp"
    elif content_type == "video/webm":
        valid = content.startswith(b"\x1a\x45\xdf\xa3")
    elif content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        valid = _is_docx(content)
    elif content_type in {"text/plain", "text/csv", "application/csv", "application/vnd.ms-excel"}:
        valid = b"\x00" not in content

    if not valid:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File contents do not match the selected file type")


def _is_docx(content: bytes) -> bool:
    if not content.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            return "[Content_Types].xml" in names and "word/document.xml" in names
    except (OSError, zipfile.BadZipFile):
        return False
