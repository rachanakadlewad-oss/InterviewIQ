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
from app.db import Application, IdentityCheckRow, Job, ReviewItem, Slot, User, UserSession, jdump, jload
from app.logging_setup import setup_logging
from app.schemas import AuthResponse, JobIn, LoginIn, LogoutResponse, SessionState, SignupIn, UserOut
from app.services import auth as auth_svc
from app.services import identity as idsvc
from app.services import overview as overview_svc
from app.services import reports, scheduler
from app.services.resume_parser import ResumeParseError, parse_resume
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
    def overview(db=Depends(get_db)):
        return overview_svc.compute_overview(db)

    @app.get("/applications", dependencies=[Depends(recruiter)])
    def all_applications(db=Depends(get_db)):
        titles = {j.id: j.title for j in db.execute(select(Job)).scalars()}
        q = select(Application).order_by(Application.id)
        return [{"application_id": a.id, "job_id": a.job_id, "job_title": titles.get(a.job_id, ""), "name": a.candidate_name,
                 "email": a.email, "status": a.status, "resume_score": a.resume_score, "rank": a.rank,
                 "shortlisted": a.shortlisted, "scoring_source": a.scoring_source} for a in db.execute(q).scalars()]

    # ------------------------------------------------------------ jobs
    @app.post("/jobs", dependencies=[Depends(recruiter)])
    def create_job(job: JobIn, db=Depends(get_db)):
        j = Job(title=job.title, description=job.description, competencies_json=jdump([c.model_dump() for c in job.competencies]))
        db.add(j); db.commit()
        return {"id": j.id, "title": j.title}

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
    def list_jobs(db=Depends(get_db)):
        return [{"id": j.id, "title": j.title, "competencies": len(jload(j.competencies_json, []))}
                for j in db.execute(select(Job).order_by(Job.id)).scalars()]

    @app.get("/jobs/{job_id}", dependencies=[Depends(recruiter)])
    def get_job(job_id: int, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        return {"id": j.id, "title": j.title, "description": j.description, "competencies": jload(j.competencies_json, [])}

    class JobUpdateIn(BaseModel):
        title: Optional[str] = None
        description: Optional[str] = None

    @app.patch("/jobs/{job_id}", dependencies=[Depends(recruiter)])
    def update_job(job_id: int, body: JobUpdateIn, db=Depends(get_db)):
        j = db.get(Job, job_id)
        if not j:
            raise NotFound("job not found")
        if body.title is not None and body.title.strip():
            j.title = body.title.strip()
        if body.description is not None:
            j.description = body.description.strip()
        db.commit()
        return {"id": j.id, "title": j.title, "description": j.description}

    # ------------------------------------------------------------ resumes
    @app.post("/jobs/{job_id}/applications", dependencies=[Depends(recruiter)])
    async def upload_resume(job_id: int, file: UploadFile = File(...), photo: Optional[UploadFile] = File(None),
                            db=Depends(get_db)):
        if not db.get(Job, job_id):
            raise NotFound("job not found")
        data = await file.read()
        try:
            text, profile, embedded_photo = parse_resume(file.filename or "resume", data)
        except ResumeParseError as e:
            raise HTTPException(422, str(e))

        candidate_user = None
        if profile.email:
            candidate_user = db.execute(select(User).where(func.lower(User.email) == profile.email.strip().lower(), User.role == "candidate")).scalar_one_or_none()

        a = Application(job_id=job_id, candidate_name=profile.name, email=profile.email, status="PARSED",
                        resume_filename=file.filename or "", resume_text=text, profile_json=jdump(profile.model_dump()),
                        access_token=new_access_token(), user_id=candidate_user.id if candidate_user else None)
        db.add(a); db.flush()
        photo_bytes = (await photo.read()) if photo else embedded_photo
        if photo_bytes:
            p = s.subdir("reference_photos") / f"ref_{a.id}_{uuid.uuid4().hex[:6]}.img"
            p.write_bytes(photo_bytes)
            a.photo_path = str(p)
        db.commit()
        return {"application_id": a.id, "name": a.candidate_name, "email": a.email, "has_reference_photo": bool(a.photo_path),
                "skills": profile.skills}

    @app.get("/jobs/{job_id}/applications", dependencies=[Depends(recruiter)])
    def list_apps(job_id: int, db=Depends(get_db)):
        q = select(Application).where(Application.job_id == job_id).order_by(Application.rank.is_(None), Application.rank, Application.id)
        return [{"application_id": a.id, "name": a.candidate_name, "email": a.email, "status": a.status,
                 "resume_score": a.resume_score, "rank": a.rank, "shortlisted": a.shortlisted,
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

    @app.get("/portal/me")
    def me(a: Application = Depends(candidate), db=Depends(get_db)):
        sl = scheduler.slot_of(db, a.id)
        job = db.get(Job, a.job_id)
        return {"application_id": a.id, "name": a.candidate_name, "status": a.status, "job_title": job.title if job else "",
                "access_token": a.access_token,
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
