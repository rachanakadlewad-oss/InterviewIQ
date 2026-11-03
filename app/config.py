"""Central configuration. Everything is read from environment variables (.env supported)."""
import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv is optional at import time
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = str(BASE_DIR / "runtime")
DEFAULT_DB_URL = f"sqlite:///{str(BASE_DIR / 'runtime' / 'interviewiq.db').replace(chr(92), '/')}"


def _f(name, default):
    return float(os.getenv(name, default))


def _i(name, default):
    return int(os.getenv(name, default))


def _b(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    llm_provider: str = "demo"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_timeout: int = 60
    agent_max_retries: int = 2
    agent_retry_backoff: float = 0.5

    weight_resume: float = 0.4
    weight_interview: float = 0.6
    recommend_advance_min: float = 70.0
    recommend_review_min: float = 50.0

    shortlist_top_n: int = 3
    shortlist_min_score: float = 40.0

    max_questions: int = 8
    max_followups_per_competency: int = 2
    max_broad_pivots: int = 2
    planned_competencies: int = 4
    min_competencies_covered: int = 3
    min_questions_before_conclude: int = 4

    identity_backend: str = "demo"
    identity_match_threshold: float = 0.70

    data_dir: str = DEFAULT_DATA_DIR
    database_url: str = DEFAULT_DB_URL
    enforce_slot_time: bool = False
    recruiter_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        raw_data_dir = os.getenv("DATA_DIR", DEFAULT_DATA_DIR)
        data_path = Path(raw_data_dir)
        if not data_path.is_absolute():
            data_path = (BASE_DIR / data_path).resolve()

        raw_db_url = os.getenv("DATABASE_URL", "")
        if raw_db_url:
            if raw_db_url.startswith("sqlite:///./"):
                rel = raw_db_url[len("sqlite:///./"):]
                db_url = f"sqlite:///{str((BASE_DIR / rel).resolve()).replace(chr(92), '/')}"
            elif raw_db_url.startswith("sqlite:///") and not raw_db_url.startswith("sqlite:///:memory:"):
                sub = raw_db_url[len("sqlite:///"):]
                if not Path(sub).is_absolute():
                    db_url = f"sqlite:///{str((BASE_DIR / sub).resolve()).replace(chr(92), '/')}"
                else:
                    db_url = raw_db_url
            else:
                db_url = raw_db_url
        else:
            db_url = f"sqlite:///{str(data_path / 'interviewiq.db').replace(chr(92), '/')}"

        s = cls(
            llm_provider=os.getenv("LLM_PROVIDER", "demo").strip().lower(),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", ""),
            llm_timeout=_i("LLM_TIMEOUT_SECONDS", 60),
            agent_max_retries=_i("AGENT_MAX_RETRIES", 2),
            weight_resume=_f("WEIGHT_RESUME", 0.4),
            weight_interview=_f("WEIGHT_INTERVIEW", 0.6),
            recommend_advance_min=_f("RECOMMEND_ADVANCE_MIN", 70),
            recommend_review_min=_f("RECOMMEND_REVIEW_MIN", 50),
            shortlist_top_n=_i("SHORTLIST_TOP_N", 3),
            shortlist_min_score=_f("SHORTLIST_MIN_SCORE", 40),
            max_questions=_i("MAX_QUESTIONS", 8),
            max_followups_per_competency=_i("MAX_FOLLOWUPS_PER_COMPETENCY", 2),
            max_broad_pivots=_i("MAX_BROAD_PIVOTS", 2),
            planned_competencies=_i("PLANNED_COMPETENCIES", 4),
            min_competencies_covered=_i("MIN_COMPETENCIES_COVERED", 3),
            min_questions_before_conclude=_i("MIN_QUESTIONS_BEFORE_CONCLUDE", 4),
            identity_backend=os.getenv("IDENTITY_BACKEND", "demo").strip().lower(),
            identity_match_threshold=_f("IDENTITY_MATCH_THRESHOLD", 0.70),
            data_dir=str(data_path),
            database_url=db_url,
            enforce_slot_time=_b("ENFORCE_SLOT_TIME", False),
            recruiter_api_key=os.getenv("RECRUITER_API_KEY", ""),
        )
        s.validate()
        return s

    def validate(self):
        if self.llm_provider not in ("demo", "openai", "anthropic"):
            raise ValueError("LLM_PROVIDER must be demo, openai or anthropic")
        if self.llm_provider != "demo" and not self.llm_api_key and "localhost" not in self.llm_base_url:
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER is not 'demo'")
        if abs(self.weight_resume + self.weight_interview - 1.0) > 1e-6:
            raise ValueError("WEIGHT_RESUME + WEIGHT_INTERVIEW must equal 1.0")
        if self.identity_backend not in ("demo", "opencv_basic"):
            raise ValueError("IDENTITY_BACKEND must be demo or opencv_basic")
        if self.max_questions < 2:
            raise ValueError("MAX_QUESTIONS must be >= 2")

    # ---- derived paths ----
    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def subdir(self, name: str) -> Path:
        p = self.data_path / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def is_demo_llm(self) -> bool:
        return self.llm_provider == "demo"


_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def set_settings(s: Settings):
    """Used by tests and the API factory to inject settings."""
    global _settings
    _settings = s
