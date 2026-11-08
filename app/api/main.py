"""FastAPI backend. Authentication supports separate Recruiter and Candidate accounts (JWT sessions),
with backward-compatible support for candidate access tokens and recruiter API key."""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update

from app import db as dbm
from app.config import Settings, get_settings, set_settings
from app.db import Application, CandidateProfile, IdentityCheckRow, Job, ReviewItem, Slot, User, UserSession, jdump, jload
from app.logging_setup import setup_logging
from app.schemas import AuthResponse, ChangePasswordIn, JobIn, LoginIn, LogoutResponse, ResetPasswordIn, SessionState, SignupIn, UserOut
from app.services import auth as auth_svc
from app.services import identity as idsvc
from app.services import overview as overview_svc
from app.services import reports, scheduler
from app.services.resume_parser import ResumeParseError, parse_resume
from app.services.ai_matcher import evaluate_candidate_for_job
from app.services.state_machine import GateViolation
from app.llm.client import get_llm
from app.workflow.supervisor import NotFound, Supervisor, new_access_token

log = logging.getLogger(__name__)
SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"


def create_app(settings: Optional[Settings] = None, llm=None, identity_backend=None) -> FastAPI:
    setup_logging()
    if settings:
        set_settings(settings)
    s = get_settings()
    dbm.init_db(s.database_url)
    app = FastAPI(title="InterviewIQ", version="1.0")

    def get_db():
        db = dbm.new_session()
        try:
            yield db
        finally:
            db.close()

    def sup(db=Depends(get_db)) -> Supervisor:
        return Supervisor(db, s, llm=llm, identity_backend=identity_backend)

    # ------------------------------------------------------------ auth dependencies
    def _get_auth_header(
        authorization: Optional[str] = Header(default=None),
        x_auth_token: Optional[str] = Header(default=None),
    ) -> Optional[str]:
        if x_auth_token and x_auth_token.strip():
            return x_auth_token.strip()
        if authorization and authorization.strip():
            parts = authorization.strip().split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1]
            return authorization.strip()
        return None

    def get_current_user_optional(
        auth_token: Optional[str] = Depends(_get_auth_header),
        db=Depends(get_db)
    ) -> Optional[User]:
        if not auth_token:
            return None
        try:
            payload = auth_svc.decode_access_token(auth_token, s.jwt_secret_key, algorithm=s.jwt_algorithm)
        except Exception:
            raise HTTPException(401, "Invalid or expired session token")

        jti = payload.get("jti")
        user_id = payload.get("user_id")
        if not jti or not user_id:
            raise HTTPException(401, "Malformed session token")

        sess = db.get(UserSession, jti)
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        sess_exp = sess.expires_at.replace(tzinfo=None) if (sess and sess.expires_at) else None
        if not sess or sess.revoked or (sess_exp and sess_exp < now_utc):
            raise HTTPException(401, "Session has expired or was revoked. Please log in again.")

        user = db.get(User, user_id)
        if not user or user.status != "active":
            raise HTTPException(401, "User account is not found or inactive.")
        return user

    def recruiter(
        current_user: Optional[User] = Depends(get_current_user_optional),
        x_api_key: Optional[str] = Header(default=None),
    ) -> Optional[User]:
        if current_user:
            if current_user.role != "recruiter":
                raise HTTPException(403, "Recruiter access required. Candidates are not permitted to access this resource.")
            return current_user

        if s.recruiter_api_key:
            if x_api_key and x_api_key == s.recruiter_api_key:
                return None
            raise HTTPException(401, "invalid or missing X-API-Key")

        if s.require_auth:
            raise HTTPException(401, "Authentication required. Please log in as a recruiter.")

        return None

    def candidate(
        current_user: Optional[User] = Depends(get_current_user_optional),
        x_access_token: Optional[str] = Header(default=None),
        db=Depends(get_db)
    ) -> Application:
        if current_user:
            if current_user.role != "candidate":
                raise HTTPException(403, "Candidate access required. Recruiters are not permitted to access the candidate portal.")

            if x_access_token:
                a = db.execute(select(Application).where(Application.access_token == x_access_token)).scalar_one_or_none()
                if not a:
                    raise HTTPException(401, "invalid access token")
                if a.user_id != current_user.id and (not a.email or a.email.strip().lower() != current_user.email.lower()):
                    raise HTTPException(403, "This application does not belong to your candidate account.")
                return a

            a = db.execute(
                select(Application).where(
                    (Application.user_id == current_user.id) | (func.lower(Application.email) == current_user.email.lower())
                ).order_by(Application.id.desc())
            ).scalars().first()
            if not a:
                raise HTTPException(404, "No application linked to this candidate account.")
            return a

        if x_access_token:
            a = db.execute(select(Application).where(Application.access_token == x_access_token)).scalar_one_or_none()
            if not a:
                raise HTTPException(401, "invalid access token")
            return a

        raise HTTPException(401, "Authentication required. Please sign in or provide a candidate access token.")

    # ------------------------------------------------------------ exception handlers
    @app.exception_handler(GateViolation)
    async def _gate(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={"detail": str(exc), "error": "GATE_VIOLATION"})

    @app.exception_handler(NotFound)
    async def _nf(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _val(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    # ------------------------------------------------------------ auth endpoints
    @app.post("/auth/signup", response_model=AuthResponse)
    def auth_signup(body: SignupIn, db=Depends(get_db)):
        name = body.name.strip()
        email = body.email.strip().lower()
        if not auth_svc.is_valid_email(email):
            raise HTTPException(422, "Invalid email format.")
        pw_err = auth_svc.validate_password_strength(body.password)
        if pw_err:
            raise HTTPException(422, pw_err)
        if body.password != body.confirm_password:
            raise HTTPException(422, "Passwords do not match.")

        existing = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
        if existing:
            raise HTTPException(409, f"An account with email '{email}' already exists.")

        hashed = auth_svc.hash_password(body.password)
        user = User(
            name=name,
            email=email,
            password_hash=hashed,
            role=body.role.value,
            status="active"
        )
        db.add(user)
        db.flush()

        if user.role == "candidate":
            db.execute(
                update(Application).where(func.lower(Application.email) == email).values(user_id=user.id)
            )

        token_str, session_id, expires_at = auth_svc.create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            name=user.name,
            secret_key=s.jwt_secret_key,
            expires_hours=s.jwt_expiration_hours,
            algorithm=s.jwt_algorithm
        )
        db_sess = UserSession(
            id=session_id,
            user_id=user.id,
            role=user.role,
            expires_at=expires_at,
            revoked=False
        )
        db.add(db_sess)
        db.commit()

        return AuthResponse(
            token=token_str,
            user=UserOut(
                id=user.id,
                name=user.name,
                email=user.email,
                role=user.role,
                status=user.status,
                created_at=user.created_at.isoformat()
            )
        )

    @app.post("/auth/login", response_model=AuthResponse)
    def auth_login(body: LoginIn, db=Depends(get_db)):
        email = body.email.strip().lower()
        user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
        if not user:
            raise HTTPException(401, f"No account found for '{email}'. Please select 'Create Account' above to sign up.")

        if user.role != body.role.value:
            raise HTTPException(
                403,
                f"This account is registered as a {user.role}, not a {body.role.value}. Please switch to the {user.role.title()} login."
            )

        if not auth_svc.verify_password(body.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password. Please check your credentials.")

        if user.status != "active":
            raise HTTPException(403, "Account is suspended or inactive.")

        if user.role == "candidate":
            db.execute(
                update(Application).where(
                    func.lower(Application.email) == email,
                    Application.user_id.is_(None)
                ).values(user_id=user.id)
            )

        token_str, session_id, expires_at = auth_svc.create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            name=user.name,
            secret_key=s.jwt_secret_key,
            expires_hours=s.jwt_expiration_hours,
            algorithm=s.jwt_algorithm
        )
        db_sess = UserSession(
            id=session_id,
            user_id=user.id,
            role=user.role,
            expires_at=expires_at,
            revoked=False
        )
        db.add(db_sess)
        db.commit()

        return AuthResponse(
            token=token_str,
            user=UserOut(
                id=user.id,
                name=user.name,
                email=user.email,
                role=user.role,
                status=user.status,
                created_at=user.created_at.isoformat()
            )
        )

    @app.post("/auth/logout", response_model=LogoutResponse)
    def auth_logout(
        auth_token: Optional[str] = Depends(_get_auth_header),
        db=Depends(get_db)
    ):
        if auth_token:
            try:
                payload = auth_svc.decode_access_token(auth_token, s.jwt_secret_key, algorithm=s.jwt_algorithm)
                jti = payload.get("jti")
                if jti:
                    sess = db.get(UserSession, jti)
                    if sess:
                        sess.revoked = True
                        db.commit()
            except Exception:
                pass
        return LogoutResponse(status="ok", message="Successfully logged out")

    @app.post("/auth/change-password")
    def auth_change_password(
        body: ChangePasswordIn,
        user: User = Depends(get_current_user_optional),
        db=Depends(get_db)
    ):
        if not user:
            raise HTTPException(401, "Authentication required. Please sign in.")
        if not auth_svc.verify_password(body.current_password, user.password_hash):
            raise HTTPException(401, "Current password is incorrect.")
        if body.new_password != body.confirm_new_password:
            raise HTTPException(422, "New password and confirmation do not match.")
        if body.new_password == body.current_password:
            raise HTTPException(422, "New password must be different from current password.")
        pw_err = auth_svc.validate_password_strength(body.new_password)
        if pw_err:
            raise HTTPException(422, pw_err)

        user.password_hash = auth_svc.hash_password(body.new_password)
        db.execute(
            update(UserSession).where(UserSession.user_id == user.id).values(revoked=True)
        )
        token_str, session_id, expires_at = auth_svc.create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            name=user.name,
            secret_key=s.jwt_secret_key,
            expires_hours=s.jwt_expiration_hours,
            algorithm=s.jwt_algorithm
        )
        db_sess = UserSession(
            id=session_id,
            user_id=user.id,
            role=user.role,
            expires_at=expires_at,
            revoked=False
        )
        db.add(db_sess)
        db.commit()
        return {
            "status": "ok",
            "message": "Password updated successfully.",
            "token": token_str
        }

    @app.post("/auth/reset-password")
    def auth_reset_password(
        body: ResetPasswordIn,
        db=Depends(get_db)
    ):
        email = body.email.strip().lower()
        user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
        if not user:
            return {
                "status": "ok",
                "message": "If an account exists with this email, the password has been reset."
            }
        if body.new_password != body.confirm_new_password:
            raise HTTPException(422, "New password and confirmation do not match.")
        pw_err = auth_svc.validate_password_strength(body.new_password)
        if pw_err:
            raise HTTPException(422, pw_err)

        user.password_hash = auth_svc.hash_password(body.new_password)
        db.execute(
            update(UserSession).where(UserSession.user_id == user.id).values(revoked=True)
        )
        db.commit()
        return {
            "status": "ok",
            "message": "Password reset successfully. Please sign in with your new password."
        }

    @app.get("/auth/me")
    def auth_me(user: User = Depends(get_current_user_optional)):
        if not user:
            raise HTTPException(401, "Not authenticated")
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }

    # ------------------------------------------------------------ system
    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/config")
    def config():
        llm_conn = "demo_mode" if s.is_demo_llm else ("available" if (s.llm_api_key or "localhost" in s.llm_base_url) else "missing_key")
        return {"llm_provider": s.llm_provider, "llm_model": s.llm_model or None, "demo_llm": s.is_demo_llm,
                "llm_connection_status": llm_conn,
                "identity_backend": s.identity_backend, "identity_is_demo": s.identity_backend == "demo",
                "weights": {"resume": s.weight_resume, "interview": s.weight_interview},
                "limits": {"max_questions": s.max_questions, "max_followups": s.max_followups_per_competency,
                           "max_pivots": s.max_broad_pivots, "min_competencies": s.min_competencies_covered,
                           "planned_competencies": s.planned_competencies},
                "demo_identity_scenarios": idsvc.SCENARIOS,
                # status flags only - secrets are never returned
                "llm_configured": bool(s.llm_api_key) if not s.is_demo_llm else None,
                "identity_threshold": s.identity_match_threshold, "enforce_slot_time": s.enforce_slot_time,
                "recruiter_auth_enabled": bool(s.recruiter_api_key) or s.require_auth,
                "thresholds": {"advance_min": s.recommend_advance_min, "review_min": s.recommend_review_min},
                "shortlist": {"top_n": s.shortlist_top_n, "min_score": s.shortlist_min_score}}

    @app.post("/config/test-llm")
    def test_llm_connectivity():
        try:
            active_llm = llm or get_llm(s)
            return active_llm.test_connection()
        except Exception as e:
            return {"status": "error", "provider": s.llm_provider, "model": s.llm_model, "error": str(e)}

    @app.get("/overview", dependencies=[Depends(recruiter)])
    def overview(current_user: Optional[User] = Depends(recruiter), db=Depends(get_db)):
        user_id = current_user.id if current_user else None
        return overview_svc.compute_overview(db, user_id=user_id)

    @app.get("/recruiter/candidates", dependencies=[Depends(recruiter)])
    @app.get("/applications", dependencies=[Depends(recruiter)])
    def list_recruiter_candidates(
        job_id: Optional[int] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        current_user: Optional[User] = Depends(recruiter),
        db=Depends(get_db)
    ):
        user_id = current_user.id if current_user else 1
        recruiter_job_ids = [j.id for j in db.execute(select(Job).where((Job.recruiter_id == user_id) | (Job.recruiter_id.is_(None)))).scalars()]
        titles = {j.id: j.title for j in db.execute(select(Job)).scalars()}
        companies = {j.id: getattr(j, "company", "TechCorp") or "TechCorp" for j in db.execute(select(Job)).scalars()}

        q = select(Application)
        if recruiter_job_ids:
            q = q.where(Application.job_id.in_(recruiter_job_ids))
        if job_id:
            q = q.where(Application.job_id == job_id)
        if status:
            st_up = status.upper().strip()
            if st_up in ("ACTIVE", "ACTIVE_ONLY"):
                q = q.where(Application.status != "REJECTED")
            elif st_up == "SHORTLISTED":
                q = q.where((Application.shortlisted == True) | (Application.status == "SHORTLISTED")).where(Application.status != "REJECTED")
            elif st_up == "REJECTED":
                q = q.where(Application.status == "REJECTED")
            elif st_up in ("PENDING", "PENDING_REVIEW", "UNDER_REVIEW"):
                q = q.where(Application.status.in_(["PARSED", "PENDING_REVIEW", "SCORED", "UNDER_REVIEW", "PENDING", "APPLIED"]))
            elif st_up in ("ACCEPTED", "DECIDED"):
                q = q.where(Application.status.in_(["ACCEPTED", "DECIDED"])).where(Application.status != "REJECTED")
            elif st_up == "SCHEDULED":
                q = q.where(Application.status == "SCHEDULED")
            elif st_up in ("ALL", "ALL_CANDIDATES"):
                pass  # include all
            else:
                q = q.where(Application.status == st_up)
        else:
            # Default to active candidates (exclude REJECTED from the main active listing)
            q = q.where(Application.status != "REJECTED")

        apps = db.execute(q.order_by(Application.id.desc())).scalars().all()
        results = []
        for a in apps:
            prof = jload(a.profile_json, {})
            skills = prof.get("skills", [])
            cand_name = a.candidate_name or f"Candidate #{a.id}"
            cand_email = a.email or ""

            if search and search.strip():
                term = search.strip().lower()
                matched = (
                    term in cand_name.lower() or
                    term in cand_email.lower() or
                    any(term in str(s).lower() for s in skills)
                )
                if not matched:
                    continue

            eval_info = jload(a.ai_reasoning, {})
            results.append({
                "id": a.id,
                "application_id": a.id,
                "job_id": a.job_id,
                "job_title": titles.get(a.job_id, f"Job #{a.job_id}"),
                "company": companies.get(a.job_id, "TechCorp"),
                "candidate_name": cand_name,
                "name": cand_name,
                "email": cand_email,
                "status": a.status,
                "shortlisted": bool(a.shortlisted and a.status != "REJECTED"),
                "resume_score": a.resume_score or a.ai_score,
                "ai_score": a.ai_score if a.ai_score is not None else a.resume_score,
                "ai_reasoning": eval_info,
                "ai_breakdown": eval_info,
                "scoring_source": a.scoring_source or "semantic_rules",
                "scoring_error": a.scoring_error,
                "skills": skills,
                "experience_years": prof.get("experience_years", 0),
                "experience": prof.get("experience", []),
                "education": prof.get("education", []),
                "projects": prof.get("projects", []),
                "summary": prof.get("summary", ""),
                "resume_filename": a.resume_filename,
                "resume_text": a.resume_text,
                "has_reference_photo": bool(a.photo_path),
                "access_token": a.access_token,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            })
        return results

    @app.get("/recruiter/candidates/counts", dependencies=[Depends(recruiter)])
    def get_candidate_counts(
        job_id: Optional[int] = None,
        current_user: Optional[User] = Depends(recruiter),
        db=Depends(get_db)
    ):
        user_id = current_user.id if current_user else 1
        recruiter_job_ids = [j.id for j in db.execute(select(Job).where((Job.recruiter_id == user_id) | (Job.recruiter_id.is_(None)))).scalars()]

        q = select(Application)
        if recruiter_job_ids:
            q = q.where(Application.job_id.in_(recruiter_job_ids))
        if job_id:
            q = q.where(Application.job_id == job_id)

        apps = db.execute(q).scalars().all()
        total = len(apps)
        rejected = sum(1 for a in apps if a.status == "REJECTED")
        shortlisted = sum(1 for a in apps if (a.shortlisted or a.status == "SHORTLISTED") and a.status != "REJECTED")
        accepted = sum(1 for a in apps if a.status in ("ACCEPTED", "DECIDED") and a.status != "REJECTED")
        pending = sum(1 for a in apps if a.status in ("PARSED", "PENDING_REVIEW", "SCORED", "UNDER_REVIEW", "PENDING", "APPLIED") and not a.shortlisted and a.status != "REJECTED")
        active = total - rejected

        return {
            "total": total,
            "active": active,
            "shortlisted": shortlisted,
            "pending": pending,
            "accepted": accepted,
            "rejected": rejected
        }

    class StatusUpdateIn(BaseModel):
        action: Optional[str] = None
        status: Optional[str] = None
        notes: Optional[str] = None

    @app.patch("/applications/{application_id}/status", dependencies=[Depends(recruiter)])
    @app.patch("/recruiter/applications/{application_id}/status", dependencies=[Depends(recruiter)])
    def update_application_status(application_id: int, body: StatusUpdateIn, db=Depends(get_db)):
        a = db.get(Application, application_id)
        if not a:
            raise NotFound("application not found")
        act = (body.action or body.status or "").upper()
        if act in ("SHORTLIST", "SHORTLISTED"):
            a.shortlisted = True
            a.status = "SHORTLISTED"
        elif act in ("REJECT", "REJECTED"):
            a.shortlisted = False
            a.status = "REJECTED"
            # Release any booked interview slot so rejected candidate cannot enter interview workflow
            slot = db.execute(select(Slot).where(Slot.application_id == a.id)).scalar_one_or_none()
            if slot:
                slot.application_id = None
        elif act in ("PENDING", "PENDING_REVIEW", "UNDER_REVIEW", "ACTIVE"):
            a.shortlisted = False
            a.status = "PENDING_REVIEW"
        elif act in ("ACCEPT", "ACCEPTED"):
            a.shortlisted = True
            a.status = "ACCEPTED"
        else:
            raise HTTPException(400, f"Unsupported action '{body.action or body.status}'. Supported: SHORTLIST, REJECT, PENDING, ACCEPT")
        db.commit()
        return {
            "application_id": a.id,
            "status": a.status,
            "shortlisted": a.shortlisted,
            "candidate_name": a.candidate_name
        }

    @app.post("/applications/{application_id}/rescore", dependencies=[Depends(recruiter)])
    def rescore_application(application_id: int, db=Depends(get_db)):
        a = db.get(Application, application_id)
        if not a:
            raise NotFound("application not found")
        job_row = db.get(Job, a.job_id)
        if not job_row:
            raise NotFound("job not found")
        job_dict = {
            "title": job_row.title,
            "company": getattr(job_row, "company", "TechCorp") or "TechCorp",
            "description": job_row.description or "",
            "required_skills": getattr(job_row, "required_skills", "") or "",
            "preferred_skills": getattr(job_row, "preferred_skills", "") or "",
            "experience_level": getattr(job_row, "experience_level", "Mid-level") or "Mid-level",
            "location": getattr(job_row, "location", "Remote") or "Remote",
        }
        active_llm = llm or get_llm(s)
        ai_score_val, eval_dict, explanation, source = evaluate_candidate_for_job(
            job=job_dict,
            resume_text=a.resume_text,
            profile=jload(a.profile_json, {}),
            llm=active_llm,
            settings=s
        )
        a.ai_score = ai_score_val
        a.ai_reasoning = jdump(eval_dict)
        a.resume_score = ai_score_val
        a.scoring_source = source
        db.commit()
        return {"application_id": a.id, "ai_score": a.ai_score, "ai_reasoning": eval_dict}

    # ------------------------------------------------------------ jobs
    @app.post("/jobs", dependencies=[Depends(recruiter)])
    def create_job(job: JobIn, current_user: Optional[User] = Depends(recruiter), db=Depends(get_db)):
        comps = [c.model_dump() for c in job.competencies] if job.competencies else []
        if not comps:
            skills = [sk.strip() for sk in (job.required_skills or "").split(",") if sk.strip()] or [job.title]
            for idx, sk in enumerate(skills[:4], 1):
                comps.append({
                    "id": f"c_{idx}_{sk.lower().replace(' ', '_')[:20]}",
                    "name": sk,
                    "description": f"Demonstrated expertise and hands-on capability in {sk}",
                    "weight": 1.0,
                    "rubric": {
                        "1": f"Basic theoretical awareness of {sk}",
                        "3": f"Solid working proficiency with production experience in {sk}",
                        "5": f"Advanced architectural leadership and mastery in {sk}"
                    },
                    "questions": [f"Can you describe a challenging technical problem you solved using {sk}?"],
                    "keywords": [sk]
                })

        recruiter_id = current_user.id if current_user else 1
        j = Job(
            title=job.title.strip(),
            company=job.company.strip() if job.company else "TechCorp",
            description=job.description.strip(),
            required_skills=job.required_skills.strip(),
            preferred_skills=job.preferred_skills.strip(),
            experience_level=job.experience_level.strip(),
            location=job.location.strip(),
            employment_type=job.employment_type.strip(),
            status=job.status.strip().upper(),
            recruiter_id=recruiter_id,
            competencies_json=jdump(comps)
        )
        db.add(j)
        db.commit()
        return {"id": j.id, "title": j.title, "status": j.status, "company": j.company}

    @app.post("/jobs/load-sample", dependencies=[Depends(recruiter)])
    def load_sample(db=Depends(get_db)):
        data = json.loads((SAMPLE_DIR / "sample_jd.json").read_text())
        job = JobIn.model_validate(data)
        j = Job(title=job.title, description=job.description, competencies_json=jdump([c.model_dump() for c in job.competencies]))
        db.add(j); db.commit()
        now = datetime.now()
        added = scheduler.load_calendar(db, SAMPLE_DIR / "mock_calendar.json", now=now) + scheduler.generate_slots(db, now)
        return {"id": j.id, "title": j.title, "slots_added": added}

    @app.get("/jobs", dependencies=[Depends(recruiter)])
    def list_jobs(current_user: Optional[User] = Depends(recruiter), db=Depends(get_db)):
        user_id = current_user.id if current_user else 1
        jobs = db.execute(select(Job).where((Job.recruiter_id == user_id) | (Job.recruiter_id.is_(None))).order_by(Job.id)).scalars().all()
        results = []
        for j in jobs:
            apps = db.execute(select(Application).where(Application.job_id == j.id)).scalars().all()
            results.append({
                "id": j.id,
                "title": j.title,
                "company": getattr(j, "company", "TechCorp") or "TechCorp",
                "description": j.description,
                "location": getattr(j, "location", "Remote") or "Remote",
                "experience_level": getattr(j, "experience_level", "Mid-level") or "Mid-level",
                "employment_type": getattr(j, "employment_type", "Full-time") or "Full-time",
                "required_skills": getattr(j, "required_skills", "") or "",
                "preferred_skills": getattr(j, "preferred_skills", "") or "",
                "status": getattr(j, "status", "ACTIVE") or "ACTIVE",
                "competencies": len(jload(j.competencies_json, [])),
                "applicants": len(apps),
                "shortlisted": sum(1 for a in apps if a.shortlisted or a.status == "SHORTLISTED"),
                "created_at": j.created_at.isoformat() if getattr(j, "created_at", None) else None,
            })
        return results

    @app.get("/jobs/{job_id}", dependencies=[Depends(recruiter)])
    def get_job(job_id: int, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        apps = db.execute(select(Application).where(Application.job_id == j.id)).scalars().all()
        return {
            "id": j.id,
            "title": j.title,
            "company": getattr(j, "company", "TechCorp") or "TechCorp",
            "description": j.description,
            "required_skills": getattr(j, "required_skills", "") or "",
            "preferred_skills": getattr(j, "preferred_skills", "") or "",
            "experience_level": getattr(j, "experience_level", "Mid-level") or "Mid-level",
            "location": getattr(j, "location", "Remote") or "Remote",
            "employment_type": getattr(j, "employment_type", "Full-time") or "Full-time",
            "status": getattr(j, "status", "ACTIVE") or "ACTIVE",
            "competencies": jload(j.competencies_json, []),
            "applicants": len(apps),
            "shortlisted": sum(1 for a in apps if a.shortlisted or a.status == "SHORTLISTED")
        }

    class JobUpdateIn(BaseModel):
        title: Optional[str] = None
        company: Optional[str] = None
        description: Optional[str] = None
        required_skills: Optional[str] = None
        preferred_skills: Optional[str] = None
        experience_level: Optional[str] = None
        location: Optional[str] = None
        employment_type: Optional[str] = None
        status: Optional[str] = None

    @app.patch("/jobs/{job_id}", dependencies=[Depends(recruiter)])
    def update_job(job_id: int, body: JobUpdateIn, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        skills_changed = False
        if body.title is not None and body.title.strip():
            j.title = body.title.strip()
            skills_changed = True
        if body.company is not None:
            j.company = body.company.strip()
        if body.description is not None:
            j.description = body.description.strip()
        if body.required_skills is not None:
            j.required_skills = body.required_skills.strip()
            skills_changed = True
        if body.preferred_skills is not None:
            j.preferred_skills = body.preferred_skills.strip()
        if body.experience_level is not None:
            j.experience_level = body.experience_level.strip()
        if body.location is not None:
            j.location = body.location.strip()
        if body.employment_type is not None:
            j.employment_type = body.employment_type.strip()
        if body.status is not None:
            j.status = body.status.strip().upper()

        if skills_changed:
            skills = [sk.strip() for sk in (j.required_skills or "").split(",") if sk.strip()] or [j.title]
            comps = []
            for idx, sk in enumerate(skills[:4], 1):
                comps.append({
                    "id": f"c_{idx}_{sk.lower().replace(' ', '_')[:20]}",
                    "name": sk,
                    "description": f"Demonstrated expertise and hands-on capability in {sk}",
                    "weight": 1.0,
                    "rubric": {
                        "1": f"Basic theoretical awareness of {sk}",
                        "3": f"Solid working proficiency with production experience in {sk}",
                        "5": f"Advanced architectural leadership and mastery in {sk}"
                    },
                    "questions": [f"Can you describe a challenging technical problem you solved using {sk}?"],
                    "keywords": [sk]
                })
            j.competencies_json = jdump(comps)

        db.commit()
        return {
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "status": j.status,
            "description": j.description,
            "required_skills": j.required_skills,
            "preferred_skills": j.preferred_skills,
            "location": j.location,
            "employment_type": j.employment_type,
            "experience_level": j.experience_level,
            "competencies": jload(j.competencies_json, [])
        }

    @app.delete("/jobs/{job_id}", dependencies=[Depends(recruiter)])
    def delete_job(job_id: int, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        app_rows = db.execute(select(Application).where(Application.job_id == job_id)).scalars().all()
        for a in app_rows:
            slots_to_clear = db.execute(select(Slot).where(Slot.application_id == a.id)).scalars().all()
            for sl in slots_to_clear:
                sl.application_id = None
            db.delete(a)
        db.delete(j)
        db.commit()
        return {"status": "ok", "message": f"Job #{job_id} deleted successfully"}

    @app.post("/jobs/{job_id}/toggle-status", dependencies=[Depends(recruiter)])
    def toggle_job_status(job_id: int, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        j.status = "INACTIVE" if j.status == "ACTIVE" else "ACTIVE"
        db.commit()
        return {"id": j.id, "title": j.title, "status": j.status}

    # ------------------------------------------------------------ resumes
    @app.post("/jobs/{job_id}/applications", dependencies=[Depends(recruiter)])
    async def upload_resume(job_id: int, file: UploadFile = File(...), photo: Optional[UploadFile] = File(None),
                            db=Depends(get_db)):
        job = db.get(Job, job_id)
        if not job:
            raise NotFound("job not found")
        data = await file.read()
        try:
            text, profile, embedded_photo = parse_resume(file.filename or "resume", data)
        except ResumeParseError as e:
            raise HTTPException(422, str(e))

        candidate_user = None
        if profile.email:
            candidate_user = db.execute(select(User).where(func.lower(User.email) == profile.email.strip().lower(), User.role == "candidate")).scalar_one_or_none()

        # Duplicate resume detection: check if application already exists for this job with same email or name
        existing_app = None
        if profile.email and profile.email.strip():
            existing_app = db.execute(
                select(Application).where(
                    Application.job_id == job_id,
                    func.lower(Application.email) == profile.email.strip().lower()
                )
            ).scalars().first()
        if not existing_app and profile.name and profile.name.strip():
            existing_app = db.execute(
                select(Application).where(
                    Application.job_id == job_id,
                    func.lower(Application.candidate_name) == profile.name.strip().lower()
                )
            ).scalars().first()

        if existing_app:
            a = existing_app
            a.resume_filename = file.filename or a.resume_filename
            a.resume_text = text
            a.profile_json = jdump(profile.model_dump())
            if profile.name:
                a.candidate_name = profile.name
            if profile.email:
                a.email = profile.email
            if candidate_user and not a.user_id:
                a.user_id = candidate_user.id
            if a.status in ("PARSED", "SCORING_FAILED"):
                a.status = "PENDING_REVIEW"
        else:
            cand_name = profile.name or (file.filename.rsplit(".", 1)[0].replace("_", " ").title() if file.filename else "Candidate")
            a = Application(
                job_id=job_id,
                candidate_name=cand_name,
                email=profile.email or "",
                status="PENDING_REVIEW",
                resume_filename=file.filename or "",
                resume_text=text,
                profile_json=jdump(profile.model_dump()),
                access_token=new_access_token(),
                user_id=candidate_user.id if candidate_user else None
            )
            db.add(a)
            db.flush()

        photo_bytes = (await photo.read()) if photo else embedded_photo
        if photo_bytes:
            p = s.subdir("reference_photos") / f"ref_{a.id}_{uuid.uuid4().hex[:6]}.img"
            p.write_bytes(photo_bytes)
            a.photo_path = str(p)

        # Immediate AI evaluation against the correct selected job
        job_dict = {
            "title": job.title,
            "company": getattr(job, "company", "TechCorp") or "TechCorp",
            "description": job.description or "",
            "required_skills": getattr(job, "required_skills", "") or "",
            "preferred_skills": getattr(job, "preferred_skills", "") or "",
            "experience_level": getattr(job, "experience_level", "Mid-level") or "Mid-level",
            "location": getattr(job, "location", "Remote") or "Remote",
        }
        active_llm = llm or get_llm(s)
        ai_score_val, eval_dict, explanation, source = evaluate_candidate_for_job(
            job=job_dict,
            resume_text=text,
            profile=profile.model_dump(),
            llm=active_llm,
            settings=s
        )
        a.ai_score = ai_score_val
        a.ai_reasoning = jdump(eval_dict)
        a.resume_score = ai_score_val
        a.scoring_source = source

        db.commit()
        return {"application_id": a.id, "name": a.candidate_name, "email": a.email, "has_reference_photo": bool(a.photo_path),
                "skills": profile.skills, "ai_score": a.ai_score, "recommendation": eval_dict.get("recommendation"),
                "status": a.status, "job_title": job.title}

    @app.get("/jobs/{job_id}/applications", dependencies=[Depends(recruiter)])
    def list_apps(job_id: int, db=Depends(get_db)):
        q = select(Application).where(Application.job_id == job_id).order_by(Application.rank.is_(None), Application.rank, Application.id)
        return [{"application_id": a.id, "name": a.candidate_name, "email": a.email, "status": a.status,
                 "resume_score": a.resume_score or a.ai_score, "ai_score": a.ai_score, "rank": a.rank, "shortlisted": a.shortlisted,
                 "scoring_source": a.scoring_source, "scoring_error": a.scoring_error,
                 "has_reference_photo": bool(a.photo_path), "access_token": a.access_token}
                for a in db.execute(q).scalars()]

    @app.post("/jobs/{job_id}/screen", dependencies=[Depends(recruiter)])
    def screen(job_id: int, rescore: bool = False, sv: Supervisor = Depends(sup)):
        return sv.screen_job(job_id, rescore)

    class ShortlistIn(BaseModel):
        application_ids: List[int]

    @app.post("/jobs/{job_id}/shortlist", dependencies=[Depends(recruiter)])
    def shortlist(job_id: int, body: ShortlistIn, sv: Supervisor = Depends(sup)):
        return sv.shortlist(job_id, body.application_ids)

    @app.post("/jobs/{job_id}/schedule", dependencies=[Depends(recruiter)])
    def schedule(job_id: int, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        return scheduler.schedule_shortlisted(db, s, j, now=datetime.now())

    @app.post("/calendar/load", dependencies=[Depends(recruiter)])
    def load_cal(db=Depends(get_db)):
        return {"slots_added": scheduler.load_calendar(db, SAMPLE_DIR / "mock_calendar.json", now=datetime.now())}

    @app.post("/calendar/generate", dependencies=[Depends(recruiter)])
    def generate_cal(db=Depends(get_db)):
        """Create slots for the next 5 working days (idempotent). Never touches existing bookings."""
        return {"slots_added": scheduler.generate_slots(db, datetime.now())}

    @app.get("/slots", dependencies=[Depends(recruiter)])
    def slots(db=Depends(get_db)):
        scheduler.deduplicate_slots(db)
        apps = {a.id: a for a in db.execute(select(Application)).scalars()}
        titles = {j.id: j.title for j in db.execute(select(Job)).scalars()}
        conf_dir = s.subdir("confirmations")
        out = []
        for x in db.execute(select(Slot).order_by(Slot.start, Slot.resource, Slot.id)).scalars():
            a = apps.get(x.application_id)
            out.append({"id": x.id, "resource": x.resource, "start": x.start.isoformat(), "end": x.end.isoformat(),
                        "application_id": x.application_id, "candidate": a.candidate_name if a else None,
                        "job_title": titles.get(a.job_id) if a else None, "application_status": a.status if a else None,
                        "confirmation_file": bool(a and (conf_dir / f"confirmation_{a.id}.json").exists())})
        return out

    # ------------------------------------------------------------ review queue / reports
    @app.get("/reviews", dependencies=[Depends(recruiter)])
    def reviews(status: str = "OPEN", db=Depends(get_db)):
        q = select(ReviewItem).order_by(ReviewItem.id)
        if status != "ALL":
            q = select(ReviewItem).where(ReviewItem.status == status).order_by(ReviewItem.id)
        titles = {j.id: j.title for j in db.execute(select(Job)).scalars()}
        out = []
        for r in db.execute(q).scalars():
            a = db.get(Application, r.application_id)
            sl = db.execute(select(Slot).where(Slot.application_id == r.application_id)).scalar_one_or_none()
            out.append({"id": r.id, "application_id": r.application_id, "kind": r.kind, "reason": r.reason,
                        "status": r.status, "created_at": r.created_at.isoformat(), "candidate": a.candidate_name if a else "",
                        "email": a.email if a else "", "application_status": a.status if a else "",
                        "slot": ({"start": sl.start.isoformat(), "end": sl.end.isoformat(), "resource": sl.resource} if sl else None),
                        "job_title": titles.get(a.job_id, "") if a else "", "resolution": r.resolution, "notes": r.notes,
                        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None})
        return out

    @app.get("/identity/overview", dependencies=[Depends(recruiter)])
    @app.get("/identity/candidates", dependencies=[Depends(recruiter)])
    def identity_overview(db=Depends(get_db)):
        jobs = {j.id: j.title for j in db.execute(select(Job)).scalars()}
        slots = {}
        for sl in db.execute(select(Slot)).scalars():
            if sl.application_id:
                slots[sl.application_id] = {
                    "id": sl.id, "resource": sl.resource,
                    "start": sl.start.isoformat(), "end": sl.end.isoformat()
                }

        apps = db.execute(select(Application).order_by(Application.id)).scalars().all()
        checks = db.execute(select(IdentityCheckRow).order_by(IdentityCheckRow.timestamp.desc(), IdentityCheckRow.id.desc())).scalars().all()
        checks_by_app = {}
        for c in checks:
            checks_by_app.setdefault(c.application_id, []).append({
                "id": c.id, "timestamp": c.timestamp.isoformat(), "check_type": c.check_type,
                "backend": c.backend, "face_count": c.face_count, "confidence": c.confidence,
                "threshold": c.threshold, "passed": c.passed, "inconclusive": c.inconclusive,
                "reason": c.reason, "human_override": c.human_override
            })

        reviews_list = db.execute(select(ReviewItem).order_by(ReviewItem.created_at.desc(), ReviewItem.id.desc())).scalars().all()
        open_reviews_by_app = {}
        resolved_reviews_by_app = {}
        for r in reviews_list:
            rev_dict = {
                "id": r.id, "application_id": r.application_id, "kind": r.kind,
                "reason": r.reason, "status": r.status, "created_at": r.created_at.isoformat(),
                "resolution": r.resolution, "notes": r.notes,
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None
            }
            if r.status == "OPEN":
                open_reviews_by_app[r.application_id] = rev_dict
            else:
                resolved_reviews_by_app.setdefault(r.application_id, []).append(rev_dict)

        action_required = []
        pending = []
        passed = []

        for a in apps:
            app_checks = checks_by_app.get(a.id, [])
            latest_check = app_checks[0] if app_checks else None
            open_rev = open_reviews_by_app.get(a.id)
            slot_info = slots.get(a.id)

            cand_data = {
                "application_id": a.id,
                "candidate_name": a.candidate_name or f"Application #{a.id}",
                "email": a.email or "",
                "job_title": jobs.get(a.job_id, ""),
                "application_status": a.status,
                "slot": slot_info,
                "attempts": a.identity_attempts,
                "latest_check": latest_check,
                "all_checks": app_checks,
                "open_review": open_rev,
                "resolved_reviews": resolved_reviews_by_app.get(a.id, [])
            }

            if open_rev or a.status == "HUMAN_REVIEW":
                if latest_check and latest_check.get("inconclusive"):
                    cand_data["identity_status"] = "INCONCLUSIVE"
                elif open_rev and "inconclusive" in open_rev.get("reason", "").lower():
                    cand_data["identity_status"] = "INCONCLUSIVE"
                else:
                    cand_data["identity_status"] = "FAILED"
                action_required.append(cand_data)
            elif a.status == "SCHEDULED":
                cand_data["identity_status"] = "PENDING"
                pending.append(cand_data)
            elif a.status in ("IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS", "INTERVIEW_COMPLETE", "ASSESSED", "DECIDED") or (latest_check and latest_check.get("passed")):
                cand_data["identity_status"] = "PASSED"
                passed.append(cand_data)

        resolved = []
        for r in reviews_list:
            if r.status == "RESOLVED":
                a = db.get(Application, r.application_id)
                app_checks = checks_by_app.get(r.application_id, [])
                resolved.append({
                    "id": r.id,
                    "application_id": r.application_id,
                    "candidate_name": a.candidate_name if a else f"Application #{r.application_id}",
                    "email": a.email if a else "",
                    "job_title": jobs.get(a.job_id, "") if a else "",
                    "application_status": a.status if a else "",
                    "kind": r.kind,
                    "reason": r.reason,
                    "resolution": r.resolution,
                    "notes": r.notes,
                    "created_at": r.created_at.isoformat(),
                    "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                    "all_checks": app_checks
                })

        return {
            "threshold": s.identity_match_threshold,
            "backend": s.identity_backend,
            "is_demo": s.identity_backend == "demo",
            "action_required": action_required,
            "pending": pending,
            "passed": passed,
            "resolved": resolved
        }

    class ResolveIn(BaseModel):
        resolution: str
        notes: str = ""

    @app.post("/reviews/{review_id}/resolve", dependencies=[Depends(recruiter)])
    def resolve(review_id: int, body: ResolveIn, sv: Supervisor = Depends(sup)):
        return sv.resolve_review(review_id, body.resolution, body.notes)

    @app.get("/applications/{application_id}/report", dependencies=[Depends(recruiter)])
    def report(application_id: int, sv: Supervisor = Depends(sup), db=Depends(get_db)):
        sv._app(application_id)
        rep = reports.recruiter_report(db, s, application_id, sv.traces(application_id))
        sess = sv._session(application_id)
        rep["transcript"] = ([t.model_dump() for t in SessionState.model_validate_json(sess.state_json).transcript]
                             if sess else [])
        return rep

    @app.get("/applications/{application_id}/trace", dependencies=[Depends(recruiter)])
    def trace(application_id: int, sv: Supervisor = Depends(sup)):
        sv._app(application_id)
        return sv.traces(application_id)

    class DecisionIn(BaseModel):
        decision: str
        notes: str = ""

    @app.post("/applications/{application_id}/decision", dependencies=[Depends(recruiter)])
    def decision(application_id: int, body: DecisionIn, sv: Supervisor = Depends(sup)):
        return sv.record_decision(application_id, body.decision, body.notes)

    @app.post("/applications/{application_id}/assessment/retry", dependencies=[Depends(recruiter)])
    def retry(application_id: int, sv: Supervisor = Depends(sup)):
        return sv.retry_assessment(application_id)

    @app.post("/applications/{application_id}/conduct-interview", dependencies=[Depends(recruiter)])
    def conduct_interview_endpoint(application_id: int, sv: Supervisor = Depends(sup)):
        return sv.conduct_interview(application_id)

    @app.post("/applications/{application_id}/purge-biometrics", dependencies=[Depends(recruiter)])
    def purge(application_id: int, sv: Supervisor = Depends(sup)):
        return {"deleted": sv.purge_biometrics(application_id)}

    # ------------------------------------------------------------ candidate portal
    @app.get("/portal/applications")
    def list_portal_applications(
        current_user: User = Depends(get_current_user_optional),
        db=Depends(get_db)
    ):
        if not current_user:
            raise HTTPException(401, "Authentication required")
        if current_user.role != "candidate":
            raise HTTPException(403, "Candidate access required")

        apps = db.execute(
            select(Application).where(
                (Application.user_id == current_user.id) | (func.lower(Application.email) == current_user.email.lower())
            ).order_by(Application.id.desc())
        ).scalars().all()

        jobs = {j.id: j.title for j in db.execute(select(Job)).scalars()}
        return [
            {
                "application_id": a.id,
                "job_id": a.job_id,
                "job_title": jobs.get(a.job_id, f"Job #{a.job_id}"),
                "status": a.status,
                "access_token": a.access_token,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in apps
        ]

    # ------------------------------------------------------------ candidate portal jobs & applications
    @app.get("/portal/jobs")
    def list_portal_jobs(db=Depends(get_db)):
        jobs = db.execute(select(Job).where(Job.status == "ACTIVE").order_by(Job.id.desc())).scalars().all()
        return [{
            "id": j.id,
            "title": j.title,
            "company": getattr(j, "company", "TechCorp") or "TechCorp",
            "description": j.description,
            "required_skills": getattr(j, "required_skills", "") or "",
            "preferred_skills": getattr(j, "preferred_skills", "") or "",
            "experience_level": getattr(j, "experience_level", "Mid-level") or "Mid-level",
            "location": getattr(j, "location", "Remote") or "Remote",
            "employment_type": getattr(j, "employment_type", "Full-time") or "Full-time",
            "created_at": j.created_at.isoformat() if getattr(j, "created_at", None) else None
        } for j in jobs]

    @app.post("/portal/jobs/{job_id}/apply")
    async def portal_apply_job(
        job_id: int,
        file: UploadFile = File(...),
        photo: Optional[UploadFile] = File(None),
        current_user: Optional[User] = Depends(get_current_user_optional),
        db=Depends(get_db)
    ):
        job = db.get(Job, job_id)
        if not job or getattr(job, "status", "ACTIVE") != "ACTIVE":
            raise HTTPException(400, "This job is not currently open for applications.")

        data = await file.read()
        try:
            text_resume, profile, embedded_photo = parse_resume(file.filename or "resume", data)
        except ResumeParseError as e:
            raise HTTPException(422, str(e))

        user_id = current_user.id if current_user else None
        email = (current_user.email if current_user else profile.email) or ""
        name = (current_user.name if current_user else profile.name) or "Applicant"

        # Duplicate check
        existing = None
        if user_id:
            existing = db.execute(select(Application).where(Application.job_id == job_id, Application.user_id == user_id)).scalar_one_or_none()
        elif email:
            existing = db.execute(select(Application).where(Application.job_id == job_id, func.lower(Application.email) == email.lower())).scalar_one_or_none()

        if existing:
            return {
                "application_id": existing.id,
                "job_id": job_id,
                "job_title": job.title,
                "status": existing.status,
                "shortlisted": bool(existing.shortlisted),
                "access_token": existing.access_token,
                "message": "You have already applied for this job."
            }

        a = Application(
            job_id=job_id,
            user_id=user_id,
            candidate_name=name,
            email=email,
            status="APPLIED",
            resume_filename=file.filename or "resume",
            resume_text=text_resume,
            profile_json=jdump(profile.model_dump()),
            access_token=new_access_token()
        )
        db.add(a)
        db.flush()

        photo_bytes = (await photo.read()) if photo else embedded_photo
        if photo_bytes:
            p_img = s.subdir("reference_photos") / f"ref_{a.id}_{uuid.uuid4().hex[:6]}.img"
            p_img.write_bytes(photo_bytes)
            a.photo_path = str(p_img)

        # Run AI evaluation
        job_dict = {
            "title": job.title,
            "company": getattr(job, "company", "TechCorp") or "TechCorp",
            "description": job.description or "",
            "required_skills": getattr(job, "required_skills", "") or "",
            "preferred_skills": getattr(job, "preferred_skills", "") or "",
            "experience_level": getattr(job, "experience_level", "Mid-level") or "Mid-level",
            "location": getattr(job, "location", "Remote") or "Remote",
        }
        active_llm = llm or get_llm(s)
        ai_score_val, eval_dict, explanation, source = evaluate_candidate_for_job(
            job=job_dict,
            resume_text=text_resume,
            profile=profile.model_dump(),
            llm=active_llm,
            settings=s
        )
        a.ai_score = ai_score_val
        a.ai_reasoning = jdump(eval_dict)
        a.resume_score = ai_score_val
        a.scoring_source = source
        db.commit()

        return {
            "application_id": a.id,
            "candidate_name": a.candidate_name,
            "job_title": job.title,
            "status": a.status,
            "ai_score": a.ai_score,
            "access_token": a.access_token,
            "message": "Application submitted and AI-evaluated successfully!"
        }

    @app.get("/portal/me")
    def me(a: Application = Depends(candidate), db=Depends(get_db)):
        sl = scheduler.slot_of(db, a.id)
        job = db.get(Job, a.job_id)
        return {"application_id": a.id, "name": a.candidate_name, "status": a.status, "job_title": job.title if job else "",
                "access_token": a.access_token, "ai_score": a.ai_score,
                "max_questions": s.max_questions, "slot": ({"start": sl.start.isoformat(), "end": sl.end.isoformat()} if sl else None),
                "identity_backend": s.identity_backend, "identity_is_demo": s.identity_backend == "demo",
                "demo_identity_scenarios": idsvc.SCENARIOS if s.identity_backend == "demo" else []}

    @app.post("/portal/identity-check")
    async def identity_check(a: Application = Depends(candidate), frame: Optional[UploadFile] = File(None),
                             scenario: Optional[str] = Form(None), check_type: str = Form("pre_interview"),
                             sv: Supervisor = Depends(sup)):
        if check_type not in ("pre_interview", "mid_session"):
            raise HTTPException(422, "check_type must be pre_interview or mid_session")
        data = await frame.read() if frame else None
        return sv.verify_identity(a.id, data, scenario if s.identity_backend == "demo" else None, check_type)

    @app.post("/portal/interview/start")
    def start(a: Application = Depends(candidate), sv: Supervisor = Depends(sup)):
        return sv.start_interview(a.id)

    class AnswerIn(BaseModel):
        answer: str

    @app.post("/portal/interview/answer")
    def answer(body: AnswerIn, a: Application = Depends(candidate), sv: Supervisor = Depends(sup)):
        return sv.submit_answer(a.id, body.answer)

    @app.get("/portal/interview/state")
    def istate(a: Application = Depends(candidate), sv: Supervisor = Depends(sup)):
        sess = sv._session(a.id)
        if not sess:
            return {"started": False}
        st = SessionState.model_validate_json(sess.state_json)
        return {"started": True, "status": sess.status, "question": st.pending_question or None,
                "questions_asked": st.questions_asked, "max_questions": s.max_questions,
                "transcript": [t.model_dump() for t in st.transcript]}

    @app.get("/portal/feedback")
    def feedback(a: Application = Depends(candidate), db=Depends(get_db)):
        return reports.candidate_feedback(db, a.id)

    @app.post("/portal/interview/retry-assessment")
    def portal_retry_assessment(a: Application = Depends(candidate), sv: Supervisor = Depends(sup)):
        return sv.retry_assessment(a.id)

    return app


def app_factory():  # uvicorn --factory app.api.main:app_factory
    return create_app()
