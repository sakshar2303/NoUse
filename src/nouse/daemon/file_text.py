"""
Filtext-extraktion för b76-källor.
Stödjer vanlig text samt PDF (via pypdf).
"""
from __future__ import annotations

from pathlib import Path


def extract_text(path: Path) -> str:
    """
    Extrahera text från fil.
    Returnerar tom sträng vid fel.
    """
    try:
        if path.suffix.lower() == ".pdf":
            return _extract_pdf_text(path)
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        # Utan pypdf: returnera tom sträng istället för brus från binärdata.
        return ""

    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            if txt:
                parts.append(txt)
        return "\n\n".join(parts)
    except Exception:
        return ""
