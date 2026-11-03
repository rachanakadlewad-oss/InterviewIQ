import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add interviewiq root to sys.path
sys.path.insert(0, r"c:\Users\mkadl\Downloads\InterviewIQ-Working\interviewiq")

from app import db as dbm
from app.config import Settings, set_settings
from app.api.main import create_app
from fastapi.testclient import TestClient
from tests.helpers import ANSWER_BANK, SAMPLE

def test_full_pipeline(provider="demo", model=""):
    print(f"\n========================================================")
    print(f"RUNNING PIPELINE TEST: Provider={provider}, Model={model}")
    print(f"========================================================")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_data_dir = Path(tmpdir) / "runtime"
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        isolated_db_path = temp_data_dir / "isolated_test.db"
        isolated_db_url = f"sqlite:///{str(isolated_db_path).replace(chr(92), '/')}"
        
        settings = Settings.from_env()
        settings.data_dir = str(temp_data_dir)
        settings.database_url = isolated_db_url
        settings.llm_provider = provider
        if model:
            settings.llm_model = model
            
        # SAFETY GUARDS: Prevent accidental execution against the active application database
        default_settings = Settings.from_env()
        assert settings.database_url != default_settings.database_url, (
            "SAFETY ERROR: E2E test attempted to run against active application database URL!"
        )
        assert "interviewiq.db" not in settings.database_url, (
            "SAFETY ERROR: E2E test attempted to run against runtime/interviewiq.db!"
        )
        print(f"Safety check passed: using isolated test database at {isolated_db_url}")
        
        app = create_app(settings)
        client = TestClient(app)
        
        try:
            # 1. Health and Config
            assert client.get("/health").json() == {"status": "ok"}
            cfg = client.get("/config").json()
            print(f"[1/11] Config verified: provider={cfg['llm_provider']}, is_demo={cfg['demo_llm']}")
            
            # Test LLM connectivity endpoint
            conn = client.post("/config/test-llm").json()
            print(f"       LLM Connectivity: {conn.get('status')} - {conn.get('message', conn.get('error'))}")
            if provider != "demo":
                assert conn.get("status") == "ok", f"Live LLM connectivity failed: {conn}"
            
            # 2. Job Creation & Calendar Slot Setup
            job = client.post("/jobs/load-sample").json()
            job_id = job["id"]
            job_detail = client.get(f"/jobs/{job_id}").json()
            print(f"[2/11] Sample Job loaded: '{job['title']}' (ID: {job_id}) with {len(job_detail.get('competencies', []))} competencies")
            
            client.post("/calendar/generate")
            slots = client.get("/slots").json()
            assert len(slots) > 0
            print(f"       Calendar slots available: {len(slots)}")
            
            # 3. Resume Upload
            f_path = SAMPLE / "resumes" / "Aarav_Mehta.docx"
            up_res = client.post(f"/jobs/{job_id}/applications", files={"file": ("Aarav_Mehta.docx", f_path.read_bytes())})
            assert up_res.status_code == 200
            app_id = up_res.json()["application_id"]
            print(f"[3/11] Resume uploaded: Aarav_Mehta.docx -> Application ID #{app_id}")
            
            # 4. Resume Screening & Scoring
            screen_res = client.post(f"/jobs/{job_id}/screen").json()
            assert app_id in screen_res.get("scored", [])
            app_info = client.get(f"/jobs/{job_id}/applications").json()[0]
            resume_score = app_info["resume_score"]
            source = app_info["scoring_source"]
            assert resume_score is not None and resume_score > 0
            print(f"[4/11] Resume scored: {resume_score:.1f}/100 (Source: {source})")
            
            # 5. Shortlisting
            sl_res = client.post(f"/jobs/{job_id}/shortlist", json={"application_ids": [app_id]})
            assert sl_res.status_code == 200
            print(f"[5/11] Shortlist confirmed for Application #{app_id}")
            
            # 6. Scheduling into Calendar Slot
            sched_res = client.post(f"/jobs/{job_id}/schedule").json()
            assert len(sched_res) == 1 and sched_res[0]["scheduled"] is True
            access_token = sched_res[0]["access_token"]
            H = {"X-Access-Token": access_token}
            print(f"[6/11] Interview scheduled. Access token obtained: {access_token[:6]}...")
            
            # 7. Identity Verification Gate Checks
            # Gate check 1: Before verification, interview cannot start
            start_early = client.post("/portal/interview/start", headers=H)
            assert start_early.status_code == 409, "Gate check failed: allowed start before verification"
            print(f"[7/11] Gate test 1 passed: Interview start refused prior to identity check (HTTP 409)")
            
            # Gate check 2: Failed identity check locks interview and routes to human review
            fail_chk = client.post("/portal/identity-check", headers=H, data={"scenario": "different_person"}).json()
            assert fail_chk["passed"] is False
            start_failed = client.post("/portal/interview/start", headers=H)
            assert start_failed.status_code == 409
            print(f"       Gate test 2 passed: Failed verification routed to HUMAN_REVIEW, interview locked")
            
            # Human Review Resolution
            rev = client.get("/reviews").json()[0]
            assert rev["application_id"] == app_id
            res_err = client.post(f"/reviews/{rev['id']}/resolve", json={"resolution": "approve_manual_pass", "notes": ""})
            assert res_err.status_code == 422, "Validation failed: allowed resolution without mandatory notes"
            
            res_ok = client.post(f"/reviews/{rev['id']}/resolve", json={"resolution": "approve_manual_pass", "notes": "Verified via passport video call"})
            assert res_ok.status_code == 200
            print(f"       Gate test 3 passed: Recruiter manual override with mandatory note unlocked gate")
            
            # 8. Start Spoken Interview Session
            start_ok = client.post("/portal/interview/start", headers=H).json()
            assert "question" in start_ok and start_ok["question"]
            print(f"[8/11] Interview started. Opening question: \"{start_ok['question'][:70]}...\"")
            
            # 9. Turn-by-Turn Dynamic Interview Loop
            cur = start_ok
            turn = 1
            while not cur.get("concluded") and turn <= 10:
                cid = cur.get("competency_id", "python")
                answer = ANSWER_BANK.get(cid, "I have extensive experience designing architectures, implementing solutions, and verifying metrics.")
                cur = client.post("/portal/interview/answer", headers=H, json={"answer": answer}).json()
                print(f"       Turn {turn}: Answer submitted for [{cid}] -> Decision: {cur.get('decision')} (Q: {cur.get('questions_asked')})")
                turn += 1
                if provider != "demo":
                    import time
                    time.sleep(1.5)
            assert cur.get("concluded") is True, "Interview failed to conclude within question budget"
            print(f"[9/11] Interview concluded successfully in {turn-1} turns.")
            
            # 10. Assessment Verification & 40/60 Weighted Score Verification
            rep = client.get(f"/applications/{app_id}/report").json()
            asm = rep.get("assessment")
            if asm is None and rep.get("status") in ("ASSESSMENT_FAILED", "INTERVIEW_COMPLETE"):
                print(f"       Assessment initial run recorded failure: {rep.get('assessment_error')}")
                print("       Testing /applications/{id}/assessment/retry ...")
                import time
                time.sleep(3)
                ret_call = client.post(f"/applications/{app_id}/assessment/retry")
                print("       Retry status:", ret_call.json())
                rep = client.get(f"/applications/{app_id}/report").json()
                asm = rep.get("assessment")

            assert asm is not None, f"Assessment missing from report: {rep.get('assessment_error')}"
            
            w_res = rep["configured_weights"]["resume"]
            w_int = rep["configured_weights"]["interview"]
            r_score = asm["resume_score"]
            i_score = asm["interview_score"]
            f_score = asm["final_score"]
            expected_final = round((w_res * r_score) + (w_int * i_score), 1)
            
            assert f_score == expected_final, f"Scoring mismatch: expected {expected_final}, got {f_score}"
            assert asm["source"] == ("llm" if provider != "demo" else "demo_rules")
            print(f"[10/11] Assessment verified:")
            print(f"        Resume Score  ({w_res*100:.0f}%): {r_score:.1f}")
            print(f"        Interview Score ({w_int*100:.0f}%): {i_score:.1f}")
            print(f"        Final Weighted Score: {f_score:.1f} / 100 (Expected: {expected_final:.1f})")
            print(f"        Assessment Source: {asm['source']}")
            print(f"        Summary: {asm['recruiter_summary'][:100]}...")
            
            # Verify candidate feedback preview
            assert "candidate_feedback" in asm and asm["candidate_feedback"] is not None
            fb_preview = asm["candidate_feedback"]
            assert len(fb_preview.get("strengths", [])) > 0
            
            # Candidate Portal Feedback check (ensures private scores not revealed to candidate)
            cand_fb = client.get("/portal/feedback", headers=H).json()
            assert cand_fb["available"] is True
            assert "final_score" not in cand_fb
            assert "resume_score" not in cand_fb
            print(f"        Candidate Feedback Portal verified (Clean, constructive, no private score leaks)")

            # Test candidate portal retry-assessment endpoint
            cand_retry = client.post("/portal/interview/retry-assessment", headers=H).json()
            assert cand_retry.get("status") in ("ASSESSED", "DECIDED")
            print(f"        Candidate Portal retry-assessment verified: {cand_retry.get('status')}")
            
            # 11. Final Recruiter Decision
            dec_res = client.post(f"/applications/{app_id}/decision", json={"decision": "HIRE", "notes": "Candidate demonstrates outstanding competencies and verified track record."})
            assert dec_res.status_code == 200
            
            final_rep = client.get(f"/applications/{app_id}/report").json()
            assert final_rep["status"] == "DECIDED"
            assert final_rep["recruiter_decision"]["decision"] == "HIRE"
            print(f"[11/11] Final Recruiter Decision successfully recorded: HIRE")
            print(f"========================================================")
            print(f"PIPELINE TEST PASSED COMPLETELY FOR: {provider.upper()}")
            print(f"========================================================\n")
        finally:
            if dbm._engine is not None:
                dbm._engine.dispose()
            # Restore global settings back to default environment after isolated test
            set_settings(Settings.from_env())
            dbm.init_db(Settings.from_env().database_url)

if __name__ == "__main__":
    # Test 1: Deterministic Demo Mode
    test_full_pipeline(provider="demo")
    
    # Test 2: Live LLM Mode (Groq openai/gpt-oss-120b) if configured
    settings = Settings.from_env()
    if settings.llm_api_key:
        test_full_pipeline(provider="openai", model="openai/gpt-oss-120b")
    else:
        print("Skipping Live LLM Test: LLM_API_KEY not configured in .env")
