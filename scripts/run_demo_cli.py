"""Headless end-to-end demo (no server, no browser). Runs the whole pipeline in the configured mode.
    python -m scripts.run_demo_cli            # uses .env (default: DEMO mode, no API key)
It uses a throw-away database/data folder under ./runtime_cli_demo so your real data is untouched."""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import db as dbm                                            # noqa: E402
from app.config import Settings, get_settings, set_settings            # noqa: E402
from app.db import Application, Job, jdump                            # noqa: E402
from app.logging_setup import setup_logging                          # noqa: E402
from app.schemas import JobIn                                        # noqa: E402
from app.services import reports, scheduler                          # noqa: E402
from app.services.resume_parser import parse_resume                  # noqa: E402
from app.workflow.supervisor import Supervisor, new_access_token     # noqa: E402

SAMPLE = ROOT / "data" / "sample"


def main():
    setup_logging()
    base = get_settings()
    work = ROOT / "runtime_cli_demo"
    shutil.rmtree(work, ignore_errors=True)
    base.data_dir, base.database_url = str(work), f"sqlite:///{work / 'demo.db'}"
    set_settings(base)
    dbm.init_db(base.database_url)
    db = dbm.new_session()
    print(f"\n=== InterviewIQ CLI demo | LLM: {base.llm_provider.upper()}"
          f"{' (DEMO RULES - not real LLM reasoning)' if base.is_demo_llm else ''} | identity: {base.identity_backend} ===")

    jd = JobIn.model_validate(json.loads((SAMPLE / "sample_jd.json").read_text()))
    job = Job(title=jd.title, description=jd.description, competencies_json=jdump([c.model_dump() for c in jd.competencies]))
    db.add(job); db.commit()
    scheduler.load_calendar(db, SAMPLE / "mock_calendar.json")

    for f in sorted((SAMPLE / "resumes").iterdir()):
        text, prof, _ = parse_resume(f.name, f.read_bytes())
        db.add(Application(job_id=job.id, candidate_name=prof.name, email=prof.email, status="PARSED", resume_filename=f.name,
                           resume_text=text, profile_json=jdump(prof.model_dump()), access_token=new_access_token()))
    db.commit()

    sv = Supervisor(db, base)
    print("\n[Stage 1] Resume screening & ranking")
    res = sv.screen_job(job.id)
    for r in res["ranking"]:
        print(f"  #{r['rank']}  {r['name']:<16} resume score {r['total']:5.1f}/100")
    top = res["proposed_shortlist"]
    sv.shortlist(job.id, top)
    print(f"  Recruiter confirms shortlist: {top}")

    print("\n[Stage 2] Auto-scheduling (no double booking)")
    for c in scheduler.schedule_shortlisted(db, base, job, now=datetime.now()):
        print(f"  application {c['application_id']} -> slot {c.get('slot_id')} {c.get('start')} ({c.get('resource')})")

    aid = top[0]
    print(f"\n[Stage 3] Identity gate for application {aid}")
    try:
        sv.start_interview(aid)
    except Exception as e:
        print(f"  Interview before verification correctly refused: {e}")
    r = sv.verify_identity(aid, b"", "match")
    print(f"  Identity check ({r['identity']['backend']}): passed={r['passed']}  [{r['identity']['warning']}]")

    print("\n[Stage 4] Adaptive interview")
    answers = json.loads((SAMPLE / "demo_answers.json").read_text())
    out = sv.start_interview(aid)
    print(f"  Q: {out['question']}")
    seen = {}
    for i in range(20):
        cid = out["competency_id"]
        seen[cid] = seen.get(cid, 0) + 1
        # first question on a competency gets its scripted answer; follow-ups get the detailed follow-up answer
        a = answers.get(cid, answers["_generic"]) if seen[cid] == 1 else answers["_followup"]
        print(f"  A: {a[:110]}...")
        out = sv.submit_answer(aid, a)
        if out["concluded"]:
            print("  [interview concluded]")
            break
        print(f"  Q ({out['decision']}): {out['question']}")

    print("\n  Decision trace:")
    for t in sv.traces(aid):
        print(f"   turn {t['turn']}: {t['decision']:<16} trigger={t['trigger_phrase'][:55]!r} src={t['source']}"
              + (f" GUARD: {t['guard_note']}" if t['guard_note'] else ""))

    print("\n[Stage 5] Assessment & report")
    rep = reports.recruiter_report(db, base, aid, sv.traces(aid))
    a = rep["assessment"]
    print(f"  resume {a['resume_score']} | interview {a['interview_score']} | weights {a['weights']} -> FINAL {a['final_score']}  ({a['label']})")
    for f in a["flags"]:
        print("  FLAG:", f)
    print("  Candidate-facing feedback:", json.dumps(reports.candidate_feedback(db, aid), indent=2)[:600])
    sv.record_decision(aid, "ADVANCE", "Demo: human recruiter confirms.")
    print(f"\nFiles written under {work}  (identity_logs/, traces/, confirmations/)\nDone.")


if __name__ == "__main__":
    main()
