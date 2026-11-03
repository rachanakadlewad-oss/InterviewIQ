"""Deterministic Supervisor / Orchestrator (LangGraph). NOT an LLM agent.

Three compiled graphs share one PipelineState schema:
  screening  : load -> score (Recruitment Agent) -> rank
  identity   : precheck -> verify -> record -> {pass -> mark_passed | fail -> human_review}
  interview  : gate -> {start: init_session | answer: record -> decide (Interviewer Agent)
               -> {concluded -> assess (Assessment Agent + deterministic aggregation) | wait}}
Routing is plain Python; the LLM agents only produce validated proposals that the Supervisor applies."""
import json
import logging
import secrets
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.assessment import AssessmentAgent
from app.agents.base import AgentError
from app.agents.interviewer import InterviewerAgent
from app.agents.recruitment import RecruitmentAgent
from app.db import (Application, AssessmentRow, IdentityCheckRow, InterviewSessionRow, Job, RecruiterDecision,
                    ReviewItem, TraceRow, Slot, jdump, jload, utcnow)
from app.llm.client import get_llm
from app.schemas import (AssessmentOutput, IdentityResult, JobIn, ParsedProfile, SessionState, TraceEntry)
from app.services import identity as idsvc
from app.services import interview_engine as eng
from app.services import scoring
from app.services.state_machine import GateViolation, transition
from app.workflow.state import PipelineState

log = logging.getLogger(__name__)


class NotFound(Exception):
    pass


class Supervisor:
    def __init__(self, db, settings, llm=None, identity_backend=None):
        self.db, self.s = db, settings
        self.llm = llm or get_llm(settings)
        self.identity_backend = identity_backend
        self.recruiter = RecruitmentAgent(self.llm, settings)
        self.interviewer = InterviewerAgent(self.llm, settings)
        self.assessor = AssessmentAgent(self.llm, settings)
        self.g_screen = self._build_screening()
        self.g_identity = self._build_identity()
        self.g_interview = self._build_interview()

    # ================================================================ helpers
    def _app(self, application_id) -> Application:
        a = self.db.get(Application, application_id)
        if not a:
            raise NotFound(f"application {application_id} not found")
        return a

    def _job_of(self, app) -> JobIn:
        j = self.db.get(Job, app.job_id)
        return JobIn.model_validate({"title": j.title, "description": j.description,
                                     "competencies": jload(j.competencies_json, [])})

    def _session(self, application_id) -> Optional[InterviewSessionRow]:
        return self.db.execute(select(InterviewSessionRow).where(
            InterviewSessionRow.application_id == application_id)).scalar_one_or_none()

    def identity_gate_open(self, application_id) -> bool:
        """Open iff the MOST RECENT identity check (pre-interview, mid-session or human-approved) passed."""
        last = self.db.execute(select(IdentityCheckRow).where(IdentityCheckRow.application_id == application_id)
                               .order_by(IdentityCheckRow.id.desc()).limit(1)).scalar_one_or_none()
        return bool(last and last.passed)

    def _resume_scores(self, app) -> dict:
        d = jload(app.resume_scores_json, {}) or {}
        return {s["competency_id"]: s["score"] for s in d.get("scores", [])}

    # ================================================================ 1) screening graph
    def _build_screening(self):
        g = StateGraph(PipelineState)
        g.add_node("load", self._n_load)
        g.add_node("score", self._n_score)
        g.add_node("rank", self._n_rank)
        g.add_edge(START, "load")
        g.add_conditional_edges("load", lambda st: "score" if st.get("app_ids") else "rank",
                                {"score": "score", "rank": "rank"})
        g.add_edge("score", "rank")
        g.add_edge("rank", END)
        return g.compile()

    def screen_job(self, job_id: int, rescore: bool = False) -> dict:
        if not self.db.get(Job, job_id):
            raise NotFound(f"job {job_id} not found")
        return self.g_screen.invoke({"job_id": job_id, "rescore": rescore})["result"]

    def _n_load(self, st):
        q = select(Application).where(Application.job_id == st["job_id"])
        apps = self.db.execute(q).scalars().all()
        todo = [a.id for a in apps if a.status in ("PARSED", "SCORING_FAILED") or
                (st.get("rescore") and a.status in ("SCORED", "SHORTLISTED") and a.resume_text)]
        return {"app_ids": todo, "result": {"scored": [], "failed": []}}

    def _n_score(self, st):
        res = dict(st["result"])
        job_row = self.db.get(Job, st["job_id"])
        job = JobIn.model_validate({"title": job_row.title, "description": job_row.description,
                                    "competencies": jload(job_row.competencies_json, [])})
        for aid in st["app_ids"]:
            a = self._app(aid)
            try:
                prof = self.recruiter.enhance_profile(ParsedProfile.model_validate(jload(a.profile_json, {})), a.resume_text)
                a.profile_json = jdump(prof.model_dump())
                a.candidate_name = prof.name or a.candidate_name
                a.email = prof.email or a.email
                r = self.recruiter.score_resume(job, a.resume_text)
                a.resume_scores_json = jdump(r.output.model_dump())
                a.resume_summary = r.output.summary
                a.resume_score = scoring.resume_total(job, {s.competency_id: s.score for s in r.output.scores})
                a.scoring_source, a.scoring_error = r.source, ""
                if a.status in ("PARSED", "SCORING_FAILED"):
                    transition(a, "SCORED")
                res["scored"].append(aid)
            except AgentError as e:
                a.scoring_error = str(e)
                if a.status == "PARSED":
                    transition(a, "SCORING_FAILED")
                res["failed"].append({"application_id": aid, "error": str(e)})
                log.error("scoring failed for application %s: %s", aid, e)
            self.db.commit()
        return {"result": res}

    def _n_rank(self, st):
        apps = self.db.execute(select(Application).where(Application.job_id == st["job_id"],
                               Application.resume_score.is_not(None))).scalars().all()
        ranked = scoring.rank([{"application_id": a.id, "total": a.resume_score} for a in apps])
        by_id = {a.id: a for a in apps}
        for it in ranked:
            by_id[it["application_id"]].rank = it["rank"]
        self.db.commit()
        res = dict(st.get("result") or {"scored": [], "failed": []})
        res["ranking"] = [{**it, "name": by_id[it["application_id"]].candidate_name} for it in ranked]
        res["proposed_shortlist"] = scoring.propose_shortlist(ranked, self.s.shortlist_top_n, self.s.shortlist_min_score)
        return {"result": res}

    # ---- shortlist (recruiter-confirmed; deterministic service) ----
    def shortlist(self, job_id: int, application_ids: List[int]) -> dict:
        apps = self.db.execute(select(Application).where(Application.job_id == job_id)).scalars().all()
        ids = set(application_ids)
        bad = [a.id for a in apps if a.id in ids and a.status not in ("SCORED", "SHORTLISTED")]
        if bad or not ids <= {a.id for a in apps}:
            raise GateViolation(f"only scored applications of this job can be shortlisted (offending: {bad})")
        for a in apps:
            if a.id in ids:
                a.shortlisted = True
                if a.status == "SCORED":
                    transition(a, "SHORTLISTED")
            elif a.shortlisted and a.status == "SHORTLISTED":
                a.shortlisted = False
                transition(a, "SCORED")
        self.db.commit()
        return {"shortlisted": sorted(ids)}

    # ================================================================ 2) identity graph
    def _build_identity(self):
        g = StateGraph(PipelineState)
        g.add_node("precheck", self._n_id_precheck)
        g.add_node("verify", self._n_id_verify)
        g.add_node("record", self._n_id_record)
        g.add_node("mark_passed", self._n_id_pass)
        g.add_node("human_review", self._n_id_fail)
        g.add_edge(START, "precheck")
        g.add_edge("precheck", "verify")
        g.add_edge("verify", "record")
        g.add_conditional_edges("record", lambda st: "pass" if st["identity"]["passed"] else "fail",
                                {"pass": "mark_passed", "fail": "human_review"})
        g.add_edge("mark_passed", END)
        g.add_edge("human_review", END)
        return g.compile()

    def verify_identity(self, application_id: int, frame: Optional[bytes], scenario: Optional[str] = None,
                        check_type: str = "pre_interview") -> dict:
        out = self.g_identity.invoke({"application_id": application_id, "frame": frame, "scenario": scenario,
                                      "check_type": check_type})
        return out["result"]

    def _n_id_precheck(self, st):
        a = self._app(st["application_id"])
        if st["check_type"] == "pre_interview":
            if a.status != "SCHEDULED":
                raise GateViolation(f"identity check requires status SCHEDULED (current: {a.status})")
            slot = self.db.execute(select(Slot).where(Slot.application_id == a.id)).scalar_one_or_none()
            if slot is None:
                raise GateViolation("no interview slot booked for this application")
            if self.s.enforce_slot_time and datetime.now() < slot.start:
                raise GateViolation(f"too early: your slot starts at {slot.start.isoformat()}")
        elif a.status != "INTERVIEW_IN_PROGRESS":
            raise GateViolation("mid-session check only valid during an interview")
        return {"check_type": st["check_type"]}

    def _n_id_verify(self, st):
        a = self._app(st["application_id"])
        r = idsvc.verify_identity(self.s, a.photo_path, st.get("frame"), st.get("scenario"), st["check_type"],
                                  backend=self.identity_backend)
        return {"identity": r.model_dump(mode="json"), "frame": None}   # drop the frame immediately

    def _n_id_record(self, st):
        a = self._app(st["application_id"])
        r = st["identity"]
        self.db.add(IdentityCheckRow(application_id=a.id, check_type=r["check_type"], backend=r["backend"],
                                     face_count=r["face_count"], confidence=r["match_confidence"],
                                     threshold=r["threshold"], passed=r["passed"], inconclusive=r["inconclusive"],
                                     reason=r["reason"]))
        a.identity_attempts += 1
        self.db.commit()
        idsvc.append_identity_log(self.s, a.id, IdentityResult.model_validate(r))
        return {"frame": None}

    def _n_id_pass(self, st):
        a = self._app(st["application_id"])
        if st["check_type"] == "pre_interview":
            transition(a, "IDENTITY_PASSED")
            self.db.commit()
        return {"result": {"passed": True, "status": a.status, "identity": st["identity"]}}

    def _n_id_fail(self, st):
        a = self._app(st["application_id"])
        r = st["identity"]
        reason = ("INCONCLUSIVE: " if r["inconclusive"] else "FAILED: ") + r["reason"] + f" ({r['check_type']})"
        if st["check_type"] == "mid_session":
            sess = self._session(a.id)
            if sess:
                state = SessionState.model_validate_json(sess.state_json)
                state.status = "SUSPENDED"
                sess.state_json, sess.status = state.model_dump_json(), "SUSPENDED"
        transition(a, "HUMAN_REVIEW")
        self.db.add(ReviewItem(application_id=a.id, kind="IDENTITY", reason=reason))
        self.db.commit()
        return {"result": {"passed": False, "status": a.status, "identity": r,
                           "message": "Identity could not be confirmed. Your case was sent to a human reviewer; the interview will not start automatically."}}

    def resolve_review(self, review_id: int, resolution: str, notes: str) -> dict:
        item = self.db.get(ReviewItem, review_id)
        if not item or item.status != "OPEN":
            raise NotFound("open review item not found")
        a = self._app(item.application_id)
        sess = self._session(a.id)
        if resolution not in ("approve_retry", "approve_manual_pass", "reject"):
            raise ValueError("resolution must be approve_retry, approve_manual_pass or reject")
        if resolution != "approve_retry" and not notes.strip():
            raise ValueError("notes are required for manual pass / reject (accountability)")
        if resolution == "approve_retry":
            if sess:
                raise GateViolation("interview already started; use approve_manual_pass or reject")
            transition(a, "SCHEDULED")
            retry_reason = f"retry authorized: {notes}" if notes.strip() else "retry authorized"
            self.db.add(IdentityCheckRow(application_id=a.id, check_type="human_review", backend="human_reviewer",
                                         passed=False, human_override=True, reason=retry_reason,
                                         confidence=0.0, threshold=self.s.identity_match_threshold))
            idsvc.append_identity_log(self.s, a.id, IdentityResult(
                timestamp=idsvc._now(), check_type="human_review", backend="human_reviewer", passed=False,
                reason=f"RETRY AUTHORIZED: {notes}" if notes.strip() else "RETRY AUTHORIZED",
                threshold=self.s.identity_match_threshold, face_count=0, face_detected=False, single_face=False))
        elif resolution == "approve_manual_pass":
            self.db.add(IdentityCheckRow(application_id=a.id, check_type="human_review", backend="human_reviewer",
                                         passed=True, human_override=True, reason=f"manual pass: {notes}",
                                         confidence=0.0, threshold=self.s.identity_match_threshold))
            idsvc.append_identity_log(self.s, a.id, IdentityResult(
                timestamp=idsvc._now(), check_type="human_review", backend="human_reviewer", passed=True,
                human_override=True, reason=f"HUMAN OVERRIDE: {notes}",
                threshold=self.s.identity_match_threshold, face_count=1, face_detected=True, single_face=True))
            if sess and sess.status == "SUSPENDED":
                st = SessionState.model_validate_json(sess.state_json)
                st.status, sess.status = "ACTIVE", "ACTIVE"
                sess.state_json = st.model_dump_json()
                transition(a, "INTERVIEW_IN_PROGRESS")
            else:
                transition(a, "IDENTITY_PASSED")
        else:
            transition(a, "REJECTED_AT_REVIEW")
            idsvc.delete_photo(a.photo_path)
            a.photo_path = None
            self.db.add(IdentityCheckRow(application_id=a.id, check_type="human_review", backend="human_reviewer",
                                         passed=False, human_override=True, reason=f"manual rejection: {notes}",
                                         confidence=0.0, threshold=self.s.identity_match_threshold))
            idsvc.append_identity_log(self.s, a.id, IdentityResult(
                timestamp=idsvc._now(), check_type="human_review", backend="human_reviewer", passed=False,
                reason=f"HUMAN REJECT: {notes}", threshold=self.s.identity_match_threshold, face_count=0, face_detected=False, single_face=False))
        item.status, item.resolution, item.notes, item.resolved_at = "RESOLVED", resolution, notes, utcnow()
        self.db.commit()
        return {"application_id": a.id, "status": a.status}

    # ================================================================ 3) interview graph
    def _build_interview(self):
        g = StateGraph(PipelineState)
        g.add_node("gate", self._n_gate)
        g.add_node("init_session", self._n_init)
        g.add_node("record", self._n_record)
        g.add_node("decide", self._n_decide)
        g.add_node("assess", self._n_assess)
        g.add_edge(START, "gate")
        g.add_conditional_edges("gate", lambda st: st["mode"], {"start": "init_session", "answer": "record"})
        g.add_edge("init_session", END)
        g.add_edge("record", "decide")
        g.add_conditional_edges("decide", lambda st: "assess" if st.get("concluded") else "wait",
                                {"assess": "assess", "wait": END})
        g.add_edge("assess", END)
        return g.compile()

    def start_interview(self, application_id: int) -> dict:
        return self.g_interview.invoke({"mode": "start", "application_id": application_id})["result"]

    def submit_answer(self, application_id: int, answer: str) -> dict:
        if not (answer or "").strip():
            raise ValueError("answer must not be empty")
        if len(answer) > 4000:
            raise ValueError("answer too long (max 4000 characters)")
        return self.g_interview.invoke({"mode": "answer", "application_id": application_id,
                                        "answer": answer.strip()})["result"]

    def _n_gate(self, st):
        a = self._app(st["application_id"])
        if not self.identity_gate_open(a.id):
            raise GateViolation("identity verification has not passed - interview cannot start or continue")
        if st["mode"] == "start":
            if a.status != "IDENTITY_PASSED":
                raise GateViolation(f"interview can only start from IDENTITY_PASSED (current: {a.status})")
            if self._session(a.id):
                raise GateViolation("an interview session already exists for this application")
        else:
            if a.status != "INTERVIEW_IN_PROGRESS":
                raise GateViolation(f"no interview in progress (status {a.status})")
            sess = self._session(a.id)
            if not sess or sess.status != "ACTIVE":
                raise GateViolation("interview session is not active")
        return {"mode": st["mode"]}

    def _n_init(self, st):
        a = self._app(st["application_id"])
        job = self._job_of(a)
        state, trace = eng.new_state(job, self._resume_scores(a), self.s)
        transition(a, "INTERVIEW_IN_PROGRESS")
        self.db.add(InterviewSessionRow(application_id=a.id, state_json=state.model_dump_json(), status="ACTIVE"))
        self._add_trace(a.id, trace)
        self.db.commit()
        return {"result": {"question": state.pending_question, "competency": eng.name_of(state, job, state.current), "competency_id": state.current,
                           "concluded": False, "questions_asked": 1, "max_questions": self.s.max_questions}}

    def _load_state(self, a):
        sess = self._session(a.id)
        return sess, SessionState.model_validate_json(sess.state_json)

    def _n_record(self, st):
        a = self._app(st["application_id"])
        sess, state = self._load_state(a)
        eng.record_answer(state, st["answer"])
        sess.state_json = state.model_dump_json()
        self.db.commit()
        return {"answer": st["answer"]}

    def _n_decide(self, st):
        a = self._app(st["application_id"])
        job = self._job_of(a)
        sess, state = self._load_state(a)
        reason = eng.force_conclude_reason(state, self.s)
        if reason:
            trace = eng.force_conclude(state, reason)
        else:
            ctx = eng.decision_context(job, state, self.s)
            try:
                res = self.interviewer.decide(job, ctx)
                decision, source = res.output, res.source
            except AgentError as e:
                log.error("interviewer agent failed, using safe fallback: %s", e)
                decision, source = eng.fallback_decision(state, job), "fallback"
            trace = eng.apply_decision(state, job, decision, source, self.s)
        sess.state_json = state.model_dump_json()
        self._add_trace(a.id, trace)
        concluded = state.status == "CONCLUDED"
        if concluded:
            sess.status, sess.ended_at = "CONCLUDED", utcnow()
        self.db.commit()
        out = {"result": {"question": state.pending_question or None, "competency": eng.name_of(state, job, state.current), "competency_id": state.current,
                          "concluded": concluded, "decision": trace.decision.value, "questions_asked": state.questions_asked,
                          "max_questions": self.s.max_questions}, "concluded": concluded}
        return out

    def _add_trace(self, application_id, trace: TraceEntry):
        self.db.add(TraceRow(application_id=application_id, turn=trace.turn, entry_json=trace.model_dump_json()))
        self.db.flush()
        rows = self.db.execute(select(TraceRow).where(TraceRow.application_id == application_id)
                               .order_by(TraceRow.id)).scalars().all()
        p = self.s.subdir("traces") / f"interview_trace_{application_id}.json"
        p.write_text(json.dumps([json.loads(r.entry_json) for r in rows], indent=2))

    def traces(self, application_id: int) -> list:
        rows = self.db.execute(select(TraceRow).where(TraceRow.application_id == application_id)
                               .order_by(TraceRow.id)).scalars().all()
        return [json.loads(r.entry_json) for r in rows]

    # ---- assessment (Assessment Agent + deterministic aggregation) ----
    def _n_assess(self, st):
        a = self._app(st["application_id"])
        transition(a, "INTERVIEW_COMPLETE")
        self.db.commit()
        self.run_assessment(a.id)
        return {"concluded": True}

    def retry_assessment(self, application_id: int) -> dict:
        a = self._app(application_id)
        if a.status in ("ASSESSED", "DECIDED"):
            return {"status": a.status, "message": "Assessment already completed."}
        if a.status not in ("ASSESSMENT_FAILED", "INTERVIEW_COMPLETE"):
            raise GateViolation(f"assessment retry only valid from ASSESSMENT_FAILED or INTERVIEW_COMPLETE (current: {a.status})")
        self.run_assessment(a.id)
        return {"status": a.status}

    def run_assessment(self, application_id: int):
        a = self._app(application_id)
        job = self._job_of(a)
        sess, state = self._load_state(a)
        cm = eng.comp_map(job)
        answers = eng.answers_by_competency(state)
        comps = []
        for cid in state.covered:
            if cid not in answers:
                continue
            c = cm.get(cid)
            comps.append({"id": cid, "name": eng.name_of(state, job, cid), "weight": c.weight if c else 1.0,
                          "rubric": c.rubric if c else {"1": "Vague or no examples", "3": "Relevant example with some detail",
                                                        "5": "Specific, well-reasoned examples with outcomes"},
                          "keywords": c.keywords if c else [], "answers": answers[cid],
                          "planned": cid in state.planned})
        rs = self._resume_scores(a)
        traces = self.traces(a.id)
        ctx = {"job_title": job.title, "competencies": comps,
               "resume_summary": {"resume_score_0_100": a.resume_score, "per_competency": rs},
               "trace_summary": {"decisions": [t["decision"] for t in traces], "conclusion": state.conclusion_reason}}
        row = self.db.execute(select(AssessmentRow).where(AssessmentRow.application_id == a.id)).scalar_one_or_none() \
            or AssessmentRow(application_id=a.id)
        try:
            res = self.assessor.assess(ctx)
        except Exception as e:
            row.status, row.error = "FAILED", str(e)
            self.db.add(row)
            if a.status != "ASSESSMENT_FAILED":
                transition(a, "ASSESSMENT_FAILED")
            self.db.commit()
            log.error("assessment failed for %s: %s", a.id, e)
            return
        out: AssessmentOutput = res.output
        iscores = {c.competency_id: c.score for c in out.competencies}
        i_total = scoring.interview_total(job, iscores, state.planned)
        r_total = a.resume_score or 0.0
        final = scoring.combine(r_total, i_total, self.s.weight_resume, self.s.weight_interview)
        flags = []
        missing = [name for cid in state.planned if cid not in iscores for name in [eng.name_of(state, job, cid)]]
        if missing:
            flags.append(f"Planned competencies NOT assessed (no interview evidence): {missing}")
        if i_total is None:
            flags.append("No interview score available; final score equals resume score only.")
        if state.guard_overrides:
            flags.append(f"Supervisor guards overrode the interviewer agent {state.guard_overrides} time(s) (see trace).")
        if state.fallback_used:
            flags.append(f"Interviewer agent failed {state.fallback_used} time(s); safe deterministic fallback questions were used.")
        if a.scoring_source == "demo_rules" or res.source == "demo_rules":
            flags.append("DEMO MODE: scores come from keyword heuristics, not LLM reasoning.")
        if state.conclusion_reason == "question_cap":
            flags.append("Interview ended because the question cap was reached.")
        overrides = self.db.execute(select(IdentityCheckRow).where(IdentityCheckRow.application_id == a.id,
                                    IdentityCheckRow.human_override.is_(True))).scalars().all()
        if overrides:
            flags.append("Identity was manually approved by a human reviewer.")
        row.status, row.error, row.source = "OK", "", res.source
        row.output_json = out.model_dump_json()
        row.interview_scores_json = jdump(iscores)
        row.resume_score, row.interview_score, row.final_score = r_total, i_total, final
        row.label = scoring.recommendation_label(final, self.s)
        row.weights_json = jdump({"resume": self.s.weight_resume, "interview": self.s.weight_interview})
        row.flags_json = jdump(flags)
        self.db.add(row)
        if a.status in ("INTERVIEW_COMPLETE", "ASSESSMENT_FAILED"):
            transition(a, "ASSESSED")
        # data minimisation: the reference photo is no longer needed once the interview is over
        if idsvc.delete_photo(a.photo_path):
            a.photo_path = None
        self.db.commit()

    # ================================================================ recruiter decision
    def record_decision(self, application_id: int, decision: str, notes: str) -> dict:
        dec = (decision or "").strip().upper()
        if dec not in ("HIRE", "ADVANCE", "HOLD", "REJECT"):
            raise ValueError("decision must be HIRE (or ADVANCE), HOLD or REJECT")
        a = self._app(application_id)
        if a.status not in ("ASSESSED", "DECIDED"):
            raise GateViolation(f"final decision requires a completed assessment (status {a.status})")
        row = self.db.execute(select(RecruiterDecision).where(RecruiterDecision.application_id == a.id)).scalar_one_or_none()
        if row:
            row.decision, row.notes, row.decided_at = dec, notes, utcnow()
        else:
            self.db.add(RecruiterDecision(application_id=a.id, decision=dec, notes=notes))
        if a.status == "ASSESSED":
            transition(a, "DECIDED")
        self.db.commit()
        return {"application_id": a.id, "decision": dec}

    def conduct_interview(self, application_id: int, custom_answers: Optional[dict] = None) -> dict:
        """Advance candidate through the complete interview and assessment workflow:
        Scheduled -> Identity Verified -> Interview Completed -> Assessment Generated.
        """
        a = self._app(application_id)
        slot = self.db.execute(select(Slot).where(Slot.application_id == a.id)).scalar_one_or_none()
        if slot is None:
            raise GateViolation("candidate must be scheduled into an interview slot before conducting the interview")

        # 1. Identity Verification if in SCHEDULED
        if a.status == "SCHEDULED":
            id_res = self.verify_identity(a.id, b"", scenario="match", check_type="pre_interview")
            if not id_res.get("passed"):
                raise GateViolation(f"identity verification failed: {id_res}")

        if a.status not in ("IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS", "INTERVIEW_COMPLETE", "ASSESSED", "DECIDED"):
            raise GateViolation(f"cannot conduct interview from status {a.status}")

        if a.status in ("ASSESSED", "DECIDED"):
            return {"application_id": a.id, "status": a.status, "message": "Interview and assessment already completed."}

        # 2. Start session if not started
        if a.status == "IDENTITY_PASSED":
            self.start_interview(a.id)

        # 3. Load sample demo answers
        answers_file = Path("data/sample/demo_answers.json")
        if not answers_file.exists():
            answers_file = Path(self.s.data_dir).parent / "data" / "sample" / "demo_answers.json"
        answers_map = jload(answers_file.read_text(), {}) if answers_file.exists() else {}
        if custom_answers:
            answers_map.update(custom_answers)

        # 4. Turn loop: submit answers until concluded
        max_turns = self.s.max_questions + 4
        for _ in range(max_turns):
            sess, state = self._load_state(a)
            if state.status == "CONCLUDED" or a.status in ("INTERVIEW_COMPLETE", "ASSESSED", "DECIDED"):
                break
            cid = state.current
            ans = (answers_map.get(cid) or answers_map.get("_generic") or
                   "I designed and implemented the architecture, led the execution with the team, and verified the outcome with metrics.")
            out = self.submit_answer(a.id, ans)
            if out.get("concluded"):
                break

        # 5. Ensure assessment is generated
        if a.status == "INTERVIEW_COMPLETE":
            self.run_assessment(a.id)

        return {"application_id": a.id, "status": a.status}

    def purge_biometrics(self, application_id: int) -> bool:
        a = self._app(application_id)
        ok = idsvc.delete_photo(a.photo_path)
        a.photo_path = None
        self.db.commit()
        return ok


def new_access_token() -> str:
    return secrets.token_urlsafe(12)
