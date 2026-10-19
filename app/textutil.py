import re


def norm(s: str) -> str:
    """Lowercase, collapse whitespace, normalise quotes/dashes (for verbatim-evidence checks)."""
    s = (s or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2022", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def contains_quote(haystack: str, quote: str) -> bool:
    q = norm(quote).strip(" .\"'")
    return bool(q) and q in norm(haystack)


def words(s: str):
    return re.findall(r"[a-z0-9']+", (s or "").lower())


def word_count(s: str) -> int:
    return len((s or "").split())


def jaccard(a: str, b: str) -> float:
    A, B = set(words(a)), set(words(b))
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:30] or "x"


def truncate_words(s: str, n: int) -> str:
    w = s.split()
    return " ".join(w[:n])
