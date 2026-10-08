import hashlib
import json
from typing import Any

from .models import DocumentIdentity

INGESTION_VERSION = "1"
SEP = "\x1f"


def sha256(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def reader_config(reader: Any, normalize_headings: bool) -> dict[str, Any]:
    ocr = getattr(reader, "ocr", None) or getattr(reader, "_ocr", None)
    return {
        "reader": type(reader).__name__,
        "min_chars": getattr(reader, "min_chars", None) or getattr(reader, "_min_chars", None),
        "dpi": getattr(reader, "dpi", None) or getattr(reader, "_dpi", None),
        "ocr": type(ocr).__name__ if ocr is not None else None,
        "normalize_headings": normalize_headings,
    }


def reader_config_hash(reader: Any, normalize_headings: bool) -> str:
    raw = json.dumps(reader_config(reader, normalize_headings), sort_keys=True)
    return sha256(raw)


def processing_key(content_hash: str, version: str, config_hash: str) -> str:
    return sha256(SEP.join((content_hash, version, config_hash)))


def identity_for(
    regulation_id: str,
    data: bytes,
    text_fingerprint: str,
    reader: Any,
    normalize_headings: bool,
) -> DocumentIdentity:
    content = sha256(data)
    cfg = reader_config_hash(reader, normalize_headings)
    return DocumentIdentity(
        regulation_id=regulation_id,
        content_hash=content,
        text_fingerprint=text_fingerprint,
        size_bytes=len(data),
        ingestion_version=INGESTION_VERSION,
        reader_config_hash=cfg,
        processing_key=processing_key(content, INGESTION_VERSION, cfg),
    )
