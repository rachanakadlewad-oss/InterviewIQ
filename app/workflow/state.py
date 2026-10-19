"""Shared LangGraph state. Plain JSON-friendly values only; the DB session lives in the Supervisor, not the state."""
from typing import Any, Dict, List, Optional, TypedDict


class PipelineState(TypedDict, total=False):
    # inputs
    mode: str                  # interview graph: "start" | "answer"
    job_id: int
    application_id: int
    answer: str
    frame: Optional[bytes]     # live webcam frame (never persisted)
    scenario: Optional[str]    # demo identity adapter only
    rescore: bool
    check_type: str            # pre_interview | mid_session
    # working values
    app_ids: List[int]
    identity: Dict[str, Any]
    concluded: bool
    # outputs
    result: Dict[str, Any]
