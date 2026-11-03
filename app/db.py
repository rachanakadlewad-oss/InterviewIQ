"""SQLAlchemy 2.x models + session helpers (SQLite)."""
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
                        create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)  # "recruiter" or "candidate"
    status: Mapped[str] = mapped_column(String(20), default="active")  # "active", "suspended"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # jti / session token id
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    competencies_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    candidate_name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(40), default="PARSED")
    resume_filename: Mapped[str] = mapped_column(String(300), default="")
    resume_text: Mapped[str] = mapped_column(Text, default="")
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    resume_scores_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resume_summary: Mapped[str] = mapped_column(Text, default="")
    resume_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    scoring_source: Mapped[str] = mapped_column(String(20), default="")
    scoring_error: Mapped[str] = mapped_column(Text, default="")
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shortlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    access_token: Mapped[str] = mapped_column(String(64), unique=True)
    photo_path: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    identity_attempts: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Slot(Base):
    __tablename__ = "slots"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    resource: Mapped[str] = mapped_column(String(80))
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)
    # UNIQUE: one application can hold at most one slot; NULLs are allowed many times.
    application_id: Mapped[Optional[int]] = mapped_column(ForeignKey("applications.id"), nullable=True, unique=True)


class IdentityCheckRow(Base):
    __tablename__ = "identity_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    check_type: Mapped[str] = mapped_column(String(20))
    backend: Mapped[str] = mapped_column(String(30))
    face_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    inconclusive: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    human_override: Mapped[bool] = mapped_column(Boolean, default=False)


class InterviewSessionRow(Base):
    __tablename__ = "interview_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)
    state_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class TraceRow(Base):
    __tablename__ = "interview_traces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    turn: Mapped[int] = mapped_column(Integer)
    entry_json: Mapped[str] = mapped_column(Text)


class AssessmentRow(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="OK")   # OK | FAILED
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    interview_scores_json: Mapped[str] = mapped_column(Text, default="{}")
    resume_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    interview_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    final_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String(40), default="")
    weights_json: Mapped[str] = mapped_column(Text, default="{}")
    flags_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(20), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReviewItem(Base):
    __tablename__ = "review_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    kind: Mapped[str] = mapped_column(String(30), default="IDENTITY")
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="OPEN")
    resolution: Mapped[str] = mapped_column(String(30), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RecruiterDecision(Base):
    __tablename__ = "recruiter_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)
    decision: Mapped[str] = mapped_column(String(20))      # ADVANCE | HOLD | REJECT
    notes: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


_engine = None
_Session = None


def init_db(url: str):
    global _engine, _Session
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if url.startswith("sqlite:///") and ":memory:" not in url:
        from pathlib import Path
        Path(url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(url, **kwargs)
    Base.metadata.create_all(_engine)
    # Safe migration for existing SQLite database: add user_id column to applications if missing
    if url.startswith("sqlite") and ":memory:" not in url:
        try:
            with _engine.connect() as conn:
                cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(applications)").fetchall()]
                if cols and "user_id" not in cols:
                    conn.exec_driver_sql("ALTER TABLE applications ADD COLUMN user_id INTEGER REFERENCES users(id)")
                    conn.commit()
        except Exception:
            pass
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def new_session():
    if _Session is None:
        raise RuntimeError("init_db() has not been called")
    return _Session()


def jdump(o) -> str:
    return json.dumps(o, ensure_ascii=False)


def jload(s, default=None):
    try:
        return json.loads(s) if s else default
    except json.JSONDecodeError:
        return default
