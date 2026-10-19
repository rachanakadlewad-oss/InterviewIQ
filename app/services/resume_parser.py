"""Resume parsing: PDF (PyMuPDF, pypdf fallback), DOCX (python-docx), TXT -> text + structured profile (+ photo)."""
import io
import logging
import re
import zipfile
from typing import Optional, Tuple

from app.schemas import ParsedProfile

log = logging.getLogger(__name__)
MAX_BYTES = 8 * 1024 * 1024
SKILL_VOCAB = ["python", "java", "javascript", "typescript", "c++", "go", "rust", "sql", "postgresql", "mysql",
               "mongodb", "redis", "fastapi", "flask", "django", "docker", "kubernetes", "aws", "azure", "gcp",
               "terraform", "git", "linux", "pytest", "ci/cd", "jenkins", "github actions", "rest", "graphql",
               "kafka", "rabbitmq", "react", "pandas", "numpy", "tensorflow", "pytorch", "spark", "airflow",
               "celery", "microservices", "oauth", "jwt", "prometheus", "grafana", "agile", "scrum"]


class ResumeParseError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    if not data:
        raise ResumeParseError("empty file")
    if len(data) > MAX_BYTES:
        raise ResumeParseError("file too large (max 8 MB)")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if ext == "pdf":
            text = _pdf_text(data)
        elif ext == "docx":
            text = _docx_text(data)
        elif ext in ("txt", "md"):
            text = data.decode("utf-8", errors="replace")
        else:
            raise ResumeParseError(f"unsupported file type '.{ext}' (use PDF, DOCX or TXT)")
    except ResumeParseError:
        raise
    except Exception as e:
        raise ResumeParseError(f"could not read {filename}: {e}") from e
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < 30:
        raise ResumeParseError("no extractable text (scanned image PDF? OCR is not supported)")
    return text


def _pdf_text(data: bytes) -> str:
    try:
        import fitz  # PyMuPDF
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(p.get_text() for p in doc)
    except ImportError:
        log.warning("PyMuPDF not installed; falling back to pypdf")
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def _docx_text(data: bytes) -> str:
    import docx
    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def extract_photo(filename: str, data: bytes) -> Optional[bytes]:
    """Best effort: largest embedded image of a PDF/DOCX. Returns None if none (recruiter may upload separately)."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if ext == "docx":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                media = [n for n in z.namelist() if n.startswith("word/media/") and n.lower().endswith((".png", ".jpg", ".jpeg"))]
                return max((z.read(n) for n in media), key=len) if media else None
        if ext == "pdf":
            import fitz
            with fitz.open(stream=data, filetype="pdf") as doc:
                best = b""
                for page in doc:
                    for img in page.get_images(full=True):
                        b = doc.extract_image(img[0]).get("image", b"")
                        if len(b) > len(best):
                            best = b
                return best or None
    except Exception as e:  # photo extraction is optional
        log.info("photo extraction skipped: %s", e)
    return None


EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")
EDU = re.compile(r"\b(b\.?tech|b\.?e\.?|b\.?sc|bachelor|m\.?tech|m\.?sc|master|ph\.?d|mba|diploma|university|institute|college)\b", re.I)


def parse_profile(text: str) -> ParsedProfile:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = ""
    for l in lines[:6]:
        if "@" not in l and len(l.split()) <= 5 and not re.search(r"\d", l) and len(l) > 2:
            name = l.strip(" ,|-")
            break
    em = EMAIL.search(text)
    email = em.group(0) if em else ""
    m = PHONE.search(text)
    phone = m.group(0).strip() if m else ""
    low = text.lower()
    skills = sorted({s for s in SKILL_VOCAB if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", low)})
    education = [l[:140] for l in lines if EDU.search(l)][:4]
    years = 0.0
    for m in re.finditer(r"(\d{1,2})\+?\s*(?:years|yrs)", low):
        years = max(years, float(m.group(1)))
    if not years:  # fall back to date ranges such as "2019 - 2023"
        spans = [(int(a), int(b)) for a, b in re.findall(r"\b((?:19|20)\d\d)\s*[-\u2013]\s*((?:19|20)\d\d)\b", text)]
        years = float(sum(max(0, b - a) for a, b in spans))
    summary = next((l for l in lines[1:12] if len(l.split()) >= 8), "")[:300]
    return ParsedProfile(name=name, email=email, phone=phone, skills=skills, education=education,
                         experience_years=min(years, 60.0), summary=summary)


def parse_resume(filename: str, data: bytes) -> Tuple[str, ParsedProfile, Optional[bytes]]:
    text = extract_text(filename, data)
    return text, parse_profile(text), extract_photo(filename, data)
