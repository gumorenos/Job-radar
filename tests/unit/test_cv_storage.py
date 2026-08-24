from __future__ import annotations

import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

from app.domains.cvs.storage import (
    CvFileError,
    content_type_for_storage_path,
    prepare_destination,
    relative_storage_path,
    resolve_storage_path,
    safe_original_filename,
    validate_stored_file,
)


def test_storage_path_is_generated_from_ids_not_original_filename(tmp_path: Path) -> None:
    profile_id = uuid4()
    cv_id = uuid4()
    relative = relative_storage_path(profile_id, cv_id, "application/pdf")
    destination = prepare_destination(tmp_path, relative)

    assert relative.as_posix() == f"cvs/{profile_id}/{cv_id}/document.pdf"
    assert destination.is_relative_to(tmp_path.resolve())
    assert destination.parent.is_dir()
    assert safe_original_filename("../../CV Final.pdf", "application/pdf") == "CV Final.pdf"


def test_resolve_storage_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(CvFileError, match="Ruta de almacenamiento"):
        resolve_storage_path(tmp_path, "../../outside.pdf")


def test_filename_extension_must_match_media_type() -> None:
    with pytest.raises(CvFileError, match="extensión"):
        safe_original_filename("resume.docx", "application/pdf")
    with pytest.raises(CvFileError, match="Tipo de archivo"):
        safe_original_filename("resume.exe", "application/octet-stream")


def test_pdf_and_utf8_text_validation(tmp_path: Path) -> None:
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.7\nminimal test content")
    validate_stored_file(pdf, "application/pdf")

    text = tmp_path / "cv.txt"
    text.write_text("Experiencia profesional", encoding="utf-8")
    validate_stored_file(text, "text/plain")

    invalid_pdf = tmp_path / "bad.pdf"
    invalid_pdf.write_bytes(b"not a pdf")
    with pytest.raises(CvFileError, match="PDF válido"):
        validate_stored_file(invalid_pdf, "application/pdf")


def test_docx_validation_requires_word_document_members(tmp_path: Path) -> None:
    valid = tmp_path / "cv.docx"
    with zipfile.ZipFile(valid, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
    validate_stored_file(
        valid,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    invalid = tmp_path / "other.docx"
    with zipfile.ZipFile(invalid, "w") as archive:
        archive.writestr("something.txt", "not a document")
    with pytest.raises(CvFileError, match="DOCX válido"):
        validate_stored_file(
            invalid,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def test_content_type_is_derived_only_from_managed_storage_suffix() -> None:
    assert content_type_for_storage_path("cvs/a/b/document.pdf") == "application/pdf"
    assert content_type_for_storage_path("cvs/a/b/document.txt") == "text/plain"
    with pytest.raises(CvFileError, match="Extensión"):
        content_type_for_storage_path("cvs/a/b/document.exe")
