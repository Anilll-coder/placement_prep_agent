"""Load a resume / profile from disk (.txt, .md or .pdf)."""

from pathlib import Path


def load_resume(path: str) -> str:
    """Return the plain text of a resume file."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"Resume not found: {p}")
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:  # pragma: no cover
            raise ImportError("Reading PDFs needs pypdf: pip install pypdf") from e
        reader = PdfReader(str(p))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    else:
        text = p.read_text(encoding="utf-8", errors="ignore")
    text = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    if not text:
        raise ValueError(f"Could not extract any text from {p} (scanned PDF?)")
    return text
