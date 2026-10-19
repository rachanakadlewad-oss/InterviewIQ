import json
from datetime import datetime
from pathlib import Path

from app.db import Application, Job, jdump
from app.llm.client import LLMError
from app.schemas import JobIn
from app.services import scheduler
from app.services.resume_parser import parse_resume
from app.workflow.supervisor import new_access_token

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"
ANSWER_BANK = json.loads((SAMPLE / "demo_answers.json").read_text())
ANSWERS = [v for k, v in ANSWER_BANK.items() if not k.startswith("_")]


class FakeLLM:
    """Scripted real-mode LLM stand-in: items are raw strings or Exceptions (raised)."""
    is_demo = False
    name = "fake"

    def __init__(self, script):
        self.script, self.calls = list(script), 0

    def complete(self, system, user):
        self.calls += 1
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item


def make_job(db) -> Job:
    jd = JobIn.model_validate(json.loads((SAMPLE / "sample_jd.json").read_text()))
    j = Job(title=jd.title, description=jd.description, competencies_json=jdump([c.model_dump() for c in jd.competencies]))
    db.add(j)
    db.commit()
    scheduler.load_calendar(db, SAMPLE / "mock_calendar.json")
    return j


def add_resume(db, job, filename, photo_path=None) -> Application:
    data = (SAMPLE / "resumes" / filename).read_bytes()
    text, profile, _ = parse_resume(filename, data)
    a = Application(job_id=job.id, candidate_name=profile.name, email=profile.email, status="PARSED",
                    resume_filename=filename, resume_text=text, profile_json=jdump(profile.model_dump()),
                    access_token=new_access_token(), photo_path=photo_path)
    db.add(a)
    db.commit()
    return a


FUTURE = datetime(2000, 1, 1)   # sample calendar is generated relative to "today"; treat all slots as future in tests
