from __future__ import annotations

import os
import zipfile
from pathlib import Path
from uuid import UUID

MAX_CV_FILE_BYTES = 10 * 1024 * 1024

_CONTENT_TYPE_TO_SUFFIX = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}
_SUFFIX_TO_CONTENT_TYPE = {suffix: media_type for media_type, suffix in _CONTENT_TYPE_TO_SUFFIX.items()}


class CvFileError(ValueError):
    """Raised when a CV file cannot be safely stored or served."""


def normalize_media_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def safe_original_filename(filename: str, media_type: str) -> str:
    suffix = _CONTENT_TYPE_TO_SUFFIX.get(media_type)
    if suffix is None:
        raise CvFileError("Tipo de archivo no permitido. Usa PDF, DOCX o TXT.")

    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = "".join(char for char in cleaned if char.isprintable() and char not in {"\x00", "/"})
    if not cleaned:
        cleaned = f"cv{suffix}"
    if not cleaned.casefold().endswith(suffix):
        raise CvFileError(f"La extensión del archivo debe ser {suffix}.")
    if len(cleaned) > 255:
        stem_limit = 255 - len(suffix)
        cleaned = f"{cleaned[:stem_limit].rstrip('.')}{suffix}"
    return cleaned


def relative_storage_path(profile_id: UUID, cv_id: UUID, media_type: str) -> Path:
    suffix = _CONTENT_TYPE_TO_SUFFIX.get(media_type)
    if suffix is None:
        raise CvFileError("Tipo de archivo no permitido. Usa PDF, DOCX o TXT.")
    return Path("cvs") / str(profile_id) / str(cv_id) / f"document{suffix}"


def resolve_storage_path(storage_root: Path, relative_path: str | Path) -> Path:
    root = storage_root.expanduser().resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise CvFileError("Ruta de almacenamiento de CV inválida.")
    return candidate


def prepare_destination(storage_root: Path, relative_path: Path) -> Path:
    destination = resolve_storage_path(storage_root, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def validate_stored_file(path: Path, media_type: str) -> None:
    if not path.is_file():
        raise CvFileError("El archivo de CV no existe.")
    size = path.stat().st_size
    if size <= 0:
        raise CvFileError("El archivo de CV está vacío.")
    if size > MAX_CV_FILE_BYTES:
        raise CvFileError("El archivo supera el límite de 10 MB.")

    if media_type == "application/pdf":
        with path.open("rb") as handle:
            if not handle.read(5).startswith(b"%PDF-"):
                raise CvFileError("El contenido no parece ser un PDF válido.")
        return

    if media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except (OSError, zipfile.BadZipFile) as exc:
            raise CvFileError("El contenido no parece ser un DOCX válido.") from exc
        required = {"[Content_Types].xml", "word/document.xml"}
        if not required.issubset(names):
            raise CvFileError("El contenido no parece ser un DOCX válido.")
        return

    if media_type == "text/plain":
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise CvFileError("El TXT debe estar codificado en UTF-8.") from exc
        if "\x00" in content:
            raise CvFileError("El TXT contiene bytes no válidos para texto.")
        return

    raise CvFileError("Tipo de archivo no permitido. Usa PDF, DOCX o TXT.")


def content_type_for_storage_path(path: str | Path) -> str:
    suffix = Path(path).suffix.casefold()
    media_type = _SUFFIX_TO_CONTENT_TYPE.get(suffix)
    if media_type is None:
        raise CvFileError("Extensión de archivo de CV no reconocida.")
    return media_type


def atomic_replace(temp_path: Path, destination: Path) -> None:
    os.chmod(temp_path, 0o600)
    temp_path.replace(destination)
    os.chmod(destination, 0o600)
