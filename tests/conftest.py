import json
from pathlib import Path

import pytest

from app import db as dbm
from app.config import Settings, set_settings
from app.schemas import JobIn

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"


@pytest.fixture
def settings(tmp_path):
    s = Settings(data_dir=str(tmp_path / "rt"), database_url=f"sqlite:///{tmp_path / 't.db'}",
                 agent_retry_backoff=0.0)
    set_settings(s)
    return s


@pytest.fixture
def db(settings):
    dbm.init_db(settings.database_url)
    session = dbm.new_session()
    yield session
    session.close()


@pytest.fixture
def job_in():
    return JobIn.model_validate(json.loads((SAMPLE / "sample_jd.json").read_text()))
