import json
from pathlib import Path

from app.agents.demo_logic import demo_resume_scores
from app.schemas import JobIn
from app.services.resume_parser import parse_resume
from app.services.scoring import resume_total
from tests.helpers import SAMPLE


def test_resume_screening_tiers_strong_average_weak():
    jd_data = json.loads((SAMPLE / "sample_jd.json").read_text())
    job = JobIn.model_validate(jd_data)

    def evaluate_file(fname):
        text, prof, _ = parse_resume(fname, (SAMPLE / "resumes" / fname).read_bytes())
        res = demo_resume_scores(jd_data, text)
        scores_by_id = {s["competency_id"]: s for s in res["scores"]}
        total = resume_total(job, {k: v["score"] for k, v in scores_by_id.items()})
        return prof, scores_by_id, total

    # 1. Strong candidates
    meera_prof, meera_scores, meera_total = evaluate_file("Meera_Iyer.pdf")
    aarav_prof, aarav_scores, aarav_total = evaluate_file("Aarav_Mehta.docx")

    # 2. Average candidates
    priya_prof, priya_scores, priya_total = evaluate_file("Priya_Nair.pdf")
    rohan_prof, rohan_scores, rohan_total = evaluate_file("Rohan_Gupta.docx")

    # 3. Weak / entry-level candidates
    sneha_prof, sneha_scores, sneha_total = evaluate_file("Sneha_Kulkarni.pdf")
    karan_prof, karan_scores, karan_total = evaluate_file("Karan_Shah.docx")

    # Ranking assertions: Strong > Average > Weak
    assert meera_total > priya_total > rohan_total > karan_total
    assert aarav_total > priya_total > rohan_total > sneha_total

    # Strong tier totals should be in realistic 70-90 range, not inflated to 100
    assert 70.0 <= meera_total <= 90.0
    assert 70.0 <= aarav_total <= 90.0

    # Average tier totals should be in 35-65 range
    assert 45.0 <= priya_total <= 65.0
    assert 30.0 <= rohan_total <= 50.0

    # Weak tier totals should be below 30
    assert sneha_total <= 25.0
    assert karan_total <= 25.0

    # Individual competency score assertions:
    # 1. No competency should casually receive 10.0
    for s in meera_scores.values():
        assert s["score"] < 10.0
    for s in aarav_scores.values():
        assert s["score"] < 10.0

    # 2. Distinguish direct evidence, partial evidence, and missing evidence
    # Aarav: Direct in Python, API Design, Databases; Missing in Leadership
    assert aarav_scores["python"]["evidence_level"] == "DIRECT"
    assert aarav_scores["api_design"]["evidence_level"] == "DIRECT"
    assert aarav_scores["databases"]["evidence_level"] == "DIRECT"
    assert aarav_scores["leadership"]["evidence_level"] == "MISSING"
    assert aarav_scores["leadership"]["score"] == 0.0
    assert aarav_scores["leadership"]["evidence"] == []

    # Meera: Direct in Leadership (led team of 4), Direct in System Design (10k req/s)
    assert meera_scores["leadership"]["evidence_level"] == "DIRECT"
    assert meera_scores["system_design"]["evidence_level"] == "DIRECT"

    # Karan: Partial in Python (introductory/college project), Partial in Testing (wrote simple unit tests)
    assert karan_scores["python"]["evidence_level"] == "PARTIAL"
    assert karan_scores["python"]["score"] <= 4.5
    assert karan_scores["testing"]["evidence_level"] == "PARTIAL"
    assert karan_scores["testing"]["score"] <= 4.5

    # 3. Explanations must clearly explain evidence and why score was awarded
    for s in aarav_scores.values():
        assert any(lvl in s["justification"] for lvl in ["Direct Evidence", "Partial Evidence", "Missing Evidence"])
