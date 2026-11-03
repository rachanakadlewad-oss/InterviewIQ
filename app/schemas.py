"""Validated schemas shared by agents, services, workflow and API.

Agents never exchange free text: every agent output is parsed into one of these models and then
passed through additional semantic checks (see app/agents/*)."""
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ----------------------------------------------------------------- job / competencies
class Competency(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1)
    description: str = ""
    weight: float = Field(default=1.0, gt=0)
    # Explicit rubric: level -> behavioural descriptor (keys "1", "3", "5" by convention).
    rubric: Dict[str, str] = Field(default_factory=dict)
    # Seed interview questions (used for opening questions / deterministic fallbacks).
    questions: List[str] = Field(default_factory=list)
    # Keyword hints. ONLY used by the deterministic demo mode; real-LLM mode ignores them.
    keywords: List[str] = Field(default_factory=list)


class JobIn(BaseModel):
    title: str = Field(min_length=2)
    description: str = ""
    competencies: List[Competency] = Field(min_length=1)

    @field_validator("competencies")
    @classmethod
    def unique_ids(cls, v):
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("competency ids must be unique")
        return v


# ----------------------------------------------------------------- resume / recruitment agent
class ParsedProfile(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    skills: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    experience_years: float = Field(default=0.0, ge=0, le=60)
    summary: str = ""
    experience: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)


class CompetencyScore(BaseModel):
    competency_id: str
    score: float = Field(ge=0, le=10)
    evidence: List[str] = Field(default_factory=list)   # verbatim resume excerpts
    justification: str = Field(min_length=3)
    evidence_level: Optional[str] = "DIRECT"             # DIRECT | PARTIAL | MISSING


class ResumeScoringOutput(BaseModel):
    scores: List[CompetencyScore]
    summary: str = ""

    @field_validator("scores")
    @classmethod
    def unique(cls, v):
        ids = [s.competency_id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate competency_id in scores")
        return v


# ----------------------------------------------------------------- interviewer agent
class InterviewAction(str, Enum):
    NARROW_FOLLOW_UP = "NARROW_FOLLOW_UP"
    BROAD_PIVOT = "BROAD_PIVOT"
    NEXT_COMPETENCY = "NEXT_COMPETENCY"
    CONCLUDE = "CONCLUDE"


class InterviewerDecision(BaseModel):
    trigger_phrase: str = Field(min_length=1)      # must be quoted from the candidate's last answer
    reasoning: str = Field(min_length=5)
    decision: InterviewAction
    # NEXT_COMPETENCY: id of a remaining planned competency (optional).
    # BROAD_PIVOT: id or name of the (planned-later, unplanned JD, or entirely new) competency explored.
    target_competency: Optional[str] = None
    question: Optional[str] = None                 # spoken aloud -> short and natural

    @model_validator(mode="after")
    def check_question(self):
        if self.decision != InterviewAction.CONCLUDE:
            q = (self.question or "").strip()
            if not q:
                raise ValueError("question is required unless decision is CONCLUDE")
            if len(q.split()) > 45:
                raise ValueError("question too long for spoken delivery (max 45 words)")
        if self.decision == InterviewAction.BROAD_PIVOT and not (self.target_competency or "").strip():
            raise ValueError("BROAD_PIVOT requires target_competency (the new competency being explored)")
        return self


class TraceEntry(BaseModel):
    turn: int
    timestamp: str
    trigger_phrase: str
    trigger_source: str = "candidate"     # candidate | plan | limit
    reasoning: str
    decision: InterviewAction
    competency: str                       # competency the asked question targets
    question_asked: str = ""
    source: str = "llm"                   # llm | demo_rules | plan | guard | fallback
    guard_note: str = ""
    agent_decision: Optional[str] = None  # what the agent proposed before guard overrides


class Turn(BaseModel):
    turn: int
    role: str          # interviewer | candidate
    text: str
    competency: str = ""


class SessionState(BaseModel):
    planned: List[str]
    current: str
    covered: List[str] = Field(default_factory=list)
    extra: Dict[str, str] = Field(default_factory=dict)   # explored non-planned competencies id->name
    followups_used: Dict[str, int] = Field(default_factory=dict)
    pivots_used: int = 0
    questions_asked: int = 0
    answers_received: int = 0
    asked_questions: List[str] = Field(default_factory=list)
    pending_question: str = ""
    transcript: List[Turn] = Field(default_factory=list)
    status: str = "ACTIVE"          # ACTIVE | CONCLUDED | SUSPENDED
    conclusion_reason: str = ""
    guard_overrides: int = 0
    fallback_used: int = 0


# ----------------------------------------------------------------- assessment agent
class InterviewCompetencyAssessment(BaseModel):
    competency_id: str
    score: float = Field(ge=0, le=10)
    evidence: List[str] = Field(default_factory=list)   # verbatim candidate-answer excerpts
    rationale: str = Field(min_length=3)


class CandidateFeedback(BaseModel):
    summary: str
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    improvement_areas: List[str] = Field(default_factory=list)


class AssessmentOutput(BaseModel):
    competencies: List[InterviewCompetencyAssessment]
    recruiter_summary: str = Field(min_length=3)
    recommendation_rationale: str = Field(min_length=3)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    candidate_feedback: CandidateFeedback

    @field_validator("competencies")
    @classmethod
    def unique(cls, v):
        ids = [c.competency_id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate competency_id")
        return v


# ----------------------------------------------------------------- identity
class IdentityResult(BaseModel):
    timestamp: str
    check_type: str = "pre_interview"      # pre_interview | mid_session
    backend: str
    is_real_biometric: bool = False
    face_detected: bool = False
    face_count: int = 0
    single_face: bool = False
    match_confidence: float = 0.0
    threshold: float = 0.7
    passed: bool = False
    inconclusive: bool = False
    reason: str = ""
    warning: str = ""
    human_override: bool = False
