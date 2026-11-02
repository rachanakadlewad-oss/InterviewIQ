"""Resume parsing: PDF (PyMuPDF, pypdf fallback), DOCX (python-docx), TXT -> text + structured profile (+ photo)."""
import io
import logging
import re
import zipfile
from typing import Optional, Tuple

from app.schemas import ParsedProfile

log = logging.getLogger(__name__)
MAX_BYTES = 8 * 1024 * 1024
SKILL_VOCAB = sorted(set([
    "python", "java", "javascript", "typescript", "c", "c++", "c#", ".net", "asp.net", "go", "rust",
    "ruby", "rails", "php", "swift", "kotlin", "scala", "sql", "postgresql", "mysql", "sqlite",
    "oracle", "mariadb", "mongodb", "redis", "cassandra", "dynamodb", "elasticsearch", "fastapi",
    "flask", "django", "spring", "spring boot", "react", "vue", "angular", "node", "nodejs",
    "express", "nest", "next.js", "docker", "kubernetes", "aws", "azure", "gcp", "terraform",
    "ansible", "helm", "git", "linux", "unix", "bash", "shell", "powershell", "pytest", "unittest",
    "ci/cd", "jenkins", "gitlab", "bitbucket", "github actions", "rest", "graphql", "grpc", "openapi",
    "swagger", "kafka", "rabbitmq", "pandas", "numpy", "scipy", "scikit-learn", "tensorflow",
    "pytorch", "keras", "spark", "airflow", "celery", "microservices", "oauth", "oauth2", "jwt",
    "owasp", "prometheus", "grafana", "datadog", "selenium", "cypress", "playwright", "postman",
    "agile", "scrum", "jira", "code review", "s3", "ec2", "lambda"
]))


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
DEGREE_PATTERN = re.compile(
    r"\b(b\.?tech(?:nology)?|b\.?e\.?|b\.?sc|b\.?s\.?|b\.?a\.?|bca|"
    r"m\.?tech(?:nology)?|m\.?e\.?|m\.?sc|m\.?s\.?|m\.?a\.?|mca|mba|ph\.?d|phd|"
    r"bachelor(?:'s)?(?:\s+of\s+[a-z\s]+)?|master(?:'s)?(?:\s+of\s+[a-z\s]+)?|"
    r"doctorate|associate(?:'s)?\s+degree|diploma(?:\s+in\s+[a-z\s]+)?)\b",
    re.I
)
INSTITUTION_PATTERN = re.compile(
    r"\b(university|institute(?:\s+of\s+[a-z\s]+)?|college|school\s+of\s+[a-z\s]+)\b",
    re.I
)
ROLE_PATTERN = re.compile(
    r"\b(Senior|Lead|Principal|Junior|Staff|Associate|Chief)?\s*"
    r"(Backend|Frontend|Full[- ]?Stack|Software|Data|DevOps|Platform|Cloud|Systems|QA|Site Reliability|SRE|Web)?\s*"
    r"(Engineer|Developer|Architect|Specialist|Intern|Lead|Manager|Programmer|Consultant)\b",
    re.I
)
DATE_SPAN_PATTERN = re.compile(
    r"\b((?:19|20)\d\d)\s*[-\u2013to]+\s*((?:19|20)\d\d|present|current)\b",
    re.I
)


def parse_profile(text: str) -> ParsedProfile:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    low = text.lower()

    # 1. Name
    name = ""
    for l in lines[:6]:
        if "@" not in l and len(l.split()) <= 5 and not re.search(r"\d", l) and len(l) > 2:
            name = l.strip(" ,|-")
            break

    # 2. Email and phone
    em = EMAIL.search(text)
    email = em.group(0) if em else ""
    m = PHONE.search(text)
    phone = m.group(0).strip() if m else ""

    # 3. Skills extraction
    skills = set()
    for s in SKILL_VOCAB:
        if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", low):
            skills.add(s)

    # Parse explicit skills sections if present
    for line in lines:
        if re.match(r"^(?:technical\s+skills|skills|technologies|tech\s+stack|core\s+competencies)\s*[:\-]", line, re.I):
            content = re.sub(r"^(?:technical\s+skills|skills|technologies|tech\s+stack|core\s+competencies)\s*[:\-]\s*", "", line, flags=re.I)
            tokens = [t.strip().lower() for t in re.split(r"[,|;•\u2022/]+", content) if t.strip()]
            for tok in tokens:
                if 2 <= len(tok) <= 25 and not re.search(r"\d{3,}", tok):
                    skills.add(tok)
    sorted_skills = sorted(skills)

    # 4. Education extraction (excludes lines like 'college project')
    edu_lines = []
    for l in lines:
        if "college project" in l.lower() or "academic project" in l.lower():
            continue
        has_degree = bool(DEGREE_PATTERN.search(l))
        has_institution = bool(INSTITUTION_PATTERN.search(l))
        if has_degree or (has_institution and any(k in l.lower() for k in ["b.tech", "m.tech", "b.sc", "degree", "graduate", "engineering", "science", "arts"])):
            clean_l = l.strip(" -\u2022*")[:140]
            if clean_l and clean_l not in edu_lines:
                edu_lines.append(clean_l)
    education = edu_lines[:4]

    # 5. Experience roles
    exp_entries = []
    for l in lines:
        if l in education or any(d in l.lower() for d in ["b.tech", "m.tech", "b.sc", "bachelor", "master"]):
            continue
        has_role = bool(ROLE_PATTERN.search(l))
        has_dates = bool(DATE_SPAN_PATTERN.search(l))
        if has_role and (has_dates or "," in l):
            clean_l = l.strip(" -\u2022*")[:140]
            if clean_l and clean_l not in exp_entries:
                exp_entries.append(clean_l)
        elif has_dates and any(term in l.lower() for term in ["engineer", "developer", "intern", "lead", "architect", "manager", "specialist"]):
            clean_l = l.strip(" -\u2022*")[:140]
            if clean_l and clean_l not in exp_entries:
                exp_entries.append(clean_l)
    experience = exp_entries[:6]

    # 6. Experience years calculation (merges overlapping spans, excludes education lines)
    years = 0.0
    for m_yr in re.finditer(r"(\d{1,2}(?:\.\d+)?)\+?\s*(?:years|yrs)\s+(?:of\s+)?experience", low):
        years = max(years, float(m_yr.group(1)))

    if not years:
        work_spans = []
        for l in lines:
            if l in education or any(d in l.lower() for d in ["b.tech", "m.tech", "degree", "college", "university"]):
                continue
            for a, b in DATE_SPAN_PATTERN.findall(l):
                start_yr = int(a)
                end_yr = 2026 if b.lower() in ("present", "current") else int(b)
                if end_yr >= start_yr:
                    work_spans.append((start_yr, end_yr))

        if work_spans:
            work_spans.sort()
            merged = []
            for s, e in work_spans:
                if not merged or s > merged[-1][1]:
                    merged.append([s, e])
                else:
                    merged[-1][1] = max(merged[-1][1], e)
            years = float(sum(e - s for s, e in merged))

    if not years:
        spans = [(int(a), int(b)) for a, b in re.findall(r"\b((?:19|20)\d\d)\s*[-\u2013]\s*((?:19|20)\d\d)\b", text)]
        years = float(sum(max(0, b - a) for a, b in spans))

    # 7. Projects extraction
    project_entries = []
    for l in lines:
        if "college project" in l.lower() or "academic project" in l.lower():
            clean_l = l.strip(" -\u2022*")[:160]
            if len(clean_l) > 15 and clean_l not in project_entries:
                project_entries.append(clean_l)
        elif re.match(r"^(?:Built|Designed|Developed|Implemented|Re-architected|Created)\s+(?:a|an|\d+)\s+", l, re.I):
            clean_l = l.strip(" -\u2022*")[:160]
            if len(clean_l) > 15 and clean_l not in project_entries:
                project_entries.append(clean_l)
    projects = project_entries[:6]

    # 8. Summary
    summary = next((l for l in lines[1:12] if len(l.split()) >= 8), "")[:300]

    return ParsedProfile(name=name, email=email, phone=phone, skills=sorted_skills, education=education,
                         experience_years=min(years, 60.0), summary=summary, experience=experience,
                         projects=projects)


def parse_resume(filename: str, data: bytes) -> Tuple[str, ParsedProfile, Optional[bytes]]:
    text = extract_text(filename, data)
    return text, parse_profile(text), extract_photo(filename, data)
