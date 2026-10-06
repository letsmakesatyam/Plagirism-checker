"""
Headless LibreOffice DOCX to PDF converter.

Converts uploaded .docx files to genuine PDF previews using headless LibreOffice
(libreoffice-writer-nogui) with strict sandboxing and caching:
1. Argument list execution with shell=False (prevents command/shell injection).
2. Per-invocation isolated temporary user installation directory (-env:UserInstallation).
3. 30-second timeout and subprocess resource protection.
4. Persistent cache keyed by original file SHA-256 and converter version in uploads/docx_previews.
5. Preserves the original .docx file unchanged.
"""
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

CONVERTER_VERSION = "v1"
CONVERSION_TIMEOUT_SECONDS = 30


class DocxConversionError(Exception):
    """Raised when DOCX conversion to PDF fails or LibreOffice is unavailable."""
    pass


def _find_libreoffice_binary() -> str | None:
    for cmd in ["soffice", "libreoffice", "/usr/bin/libreoffice", "/usr/bin/soffice"]:
        path = shutil.which(cmd)
        if path:
            return path
    return None


def get_converted_docx_pdf_path(docx_path: str) -> str:
    """
    Returns the path to a cached PDF preview for the given DOCX file,
    converting it on-demand if not already cached.
    """
    docx_file = Path(docx_path)
    if not docx_file.exists():
        raise FileNotFoundError(f"DOCX file does not exist: {docx_path}")

    # Compute content hash
    hasher = hashlib.sha256()
    with open(docx_file, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    file_hash = hasher.hexdigest()

    # Cache location in the uploads volume
    upload_root = docx_file.parent.parent  # e.g. /app/uploads
    cache_dir = upload_root / "docx_previews"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cached_pdf = cache_dir / f"{file_hash}_{CONVERTER_VERSION}.pdf"
    if cached_pdf.exists() and cached_pdf.stat().st_size > 0:
        return str(cached_pdf)

    # Locate LibreOffice
    lo_binary = _find_libreoffice_binary()
    if not lo_binary:
        raise DocxConversionError(
            "LibreOffice is not installed in the environment. "
            "Please install libreoffice-writer-nogui or view extracted text."
        )

    # Temporary directory for isolated profile and conversion output
    tmp_dir = tempfile.mkdtemp(prefix="lo_convert_")
    tmp_profile = tempfile.mkdtemp(prefix="lo_profile_")

    try:
        cmd = [
            lo_binary,
            "--headless",
            "--invisible",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            f"-env:UserInstallation=file://{tmp_profile}",
            "--convert-to",
            "pdf",
            "--outdir",
            tmp_dir,
            str(docx_file.resolve()),
        ]

        logger.info("converting_docx_to_pdf", extra={"docx": str(docx_file), "target": str(cached_pdf)})
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CONVERSION_TIMEOUT_SECONDS,
            check=False,
        )

        if result.returncode != 0:
            err_msg = result.stderr.decode("utf-8", errors="replace")
            logger.error("libreoffice_conversion_failed", extra={"code": result.returncode, "err": err_msg})
            raise DocxConversionError(f"LibreOffice exited with code {result.returncode}: {err_msg[:200]}")

        # Locate produced PDF
        expected_output = Path(tmp_dir) / f"{docx_file.stem}.pdf"
        if not expected_output.exists() or expected_output.stat().st_size == 0:
            # Fallback search for any .pdf in tmp_dir
            pdf_files = list(Path(tmp_dir).glob("*.pdf"))
            if not pdf_files:
                raise DocxConversionError("LibreOffice completed without producing an output PDF file.")
            expected_output = pdf_files[0]

        # Copy to persistent cache
        shutil.copyfile(str(expected_output), str(cached_pdf))
        return str(cached_pdf)

    except subprocess.TimeoutExpired as exc:
        logger.error("libreoffice_conversion_timeout")
        raise DocxConversionError(f"DOCX conversion timed out after {CONVERSION_TIMEOUT_SECONDS}s") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(tmp_profile, ignore_errors=True)
