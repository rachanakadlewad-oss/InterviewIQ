"""Candidate workspace. Authentication = the per-application access token; every call is scoped server-side to that
one application, so a candidate can never reach recruiter reports or other candidates."""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from .. import api, components as C, helpers as H

voice = components.declare_component("interviewiq_voice", path=str(Path(__file__).resolve().parents[2] / "voice_component"))
PAGES = ["My Application", "Interview Details", "Identity Verification", "Join Interview", "My Feedback"]


def token():
    return st.session_state.get("cand_token")


def me():
    return api.call("GET", "/portal/me", token=token(), quiet=True)


def sign_in():
    C.page_header("Candidate portal", "Sign in with the access token from your interview confirmation.", "Welcome")
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.container(border=True):
            t = st.text_input("Access token", type="password", placeholder="Paste the token you received")
            if st.button("Sign in", type="primary", use_container_width=True):
                ok, data = api.request("GET", "/portal/me", token=t.strip())
                if ok:
                    st.session_state["cand_token"] = t.strip()
                    st.rerun()
                else:
                    C.callout("error", "We could not sign you in", "Check the token and try again, or ask the recruiter to resend it.")
        st.caption("Your token only opens your own application. It does not give access to other candidates or to recruiter information.")


def render(page):
    if not token():
        sign_in()
        return
    info = me()
    if not info:
        st.session_state.pop("cand_token", None)
        C.callout("error", "Your session is no longer valid", "Please sign in again.")
        sign_in()
        return
    {"My Application": my_application, "Interview Details": interview_details, "Identity Verification": identity,
     "Join Interview": join_interview, "My Feedback": feedback}[page](info)


def sign_out_button():
    if st.sidebar.button("Sign out"):
        st.session_state.pop("cand_token", None)
        st.rerun()


# ------------------------------------------------------------------ sections
def my_application(info):
    C.page_header("My Application", f"Hello {info['name'] or 'there'} - here is where things stand.", info["job_title"] or "Candidate workspace")
    head, body, tone = H.candidate_message(info["status"])
    C.stepper(H.candidate_steps(info["status"]))
    C.callout(tone, head, body)
    if info["slot"]:
        C.kv([("Role", info["job_title"]), ("Interview slot", f"{H.fmt_dt(info['slot']['start'])} - {H.fmt_dt(info['slot']['end'], False)}"), ("Status", H.candidate_message(info['status'])[0])])
    nxt = {"SCHEDULED": "Identity Verification", "IDENTITY_PASSED": "Join Interview", "INTERVIEW_IN_PROGRESS": "Join Interview",
           "ASSESSED": "My Feedback", "DECIDED": "My Feedback"}.get(info["status"])
    if nxt:
        st.button(f"Continue to {nxt}", on_click=api.go, args=(nxt, "candidate"), type="primary")


def interview_details(info):
    C.page_header("Interview Details", "What to expect, so you can prepare.", info["job_title"] or "Candidate workspace")
    if info["slot"]:
        C.kv([("Date and time", f"{H.fmt_dt(info['slot']['start'])} - {H.fmt_dt(info['slot']['end'], False)}"), ("Format", "Spoken or typed, one question at a time"),
              ("Length", f"Up to {info['max_questions']} questions")])
    C.section("How it works")
    for t in ["An AI interviewer asks you a question and listens to your answer. It reads what you said and decides whether to dig deeper, explore something new you mentioned, or move on.",
              "You can answer by voice (Chrome or Edge, microphone permission needed) or by typing. Both work equally well.",
              "Questions are about the job's skills. Specific examples - what you did, why, and the result - make the strongest answers.",
              "A human recruiter, not the AI, makes the final hiring decision."]:
        st.markdown(f"- {t}")
    C.section("Before you start")
    for t in ["Sit somewhere quiet with good lighting; you will do a short webcam identity check first.",
              "Have your resume handy to recall projects and numbers.",
              "You will see your feedback here after the interview."]:
        st.markdown(f"- {t}")
    C.section("Your privacy")
    st.markdown("Your webcam image is compared with your resume photo and then discarded; only the result is stored. The reference photo is deleted after your interview is assessed.")
    if info["identity_is_demo"]:
        C.callout("warning", "This installation uses a demo identity check", "It simulates the outcome you choose and does not analyse your face.")


def identity(info):
    C.page_header("Identity Verification", "A quick check that you are the person who applied. It must pass before the interview can start.", info["job_title"] or "Candidate workspace")
    s = info["status"]
    if s == "SCHEDULED":
        scenario = None
        if info["identity_is_demo"]:
            C.callout("warning", "Demo identity check", "This is a demonstration adapter: pick the outcome to simulate. It is not real face verification.")
            scenario = st.selectbox("Simulated outcome", info["demo_identity_scenarios"], format_func=lambda x: x.replace("_", " ").capitalize())
        else:
            C.callout("info", "Look straight at the camera", "Only one face should be visible. Your image is not stored.")
        shot = st.camera_input("Take a photo", label_visibility="collapsed")
        if st.button("Run identity check", type="primary"):
            files = {"frame": ("frame.jpg", shot.getvalue())} if shot else None
            with st.spinner("Checking..."):
                ok, r = api.request("POST", "/portal/identity-check", token=token(), files=files, data={"scenario": scenario or "", "check_type": "pre_interview"})
            if not ok:
                C.callout("error", "The check could not be run", r)
            elif r["passed"]:
                C.callout("success", "Identity confirmed", "You can now join the interview.")
                st.button("Go to Join Interview", on_click=api.go, args=("Join Interview", "candidate"), type="primary")
            else:
                C.callout("warning", "We could not confirm your identity", r.get("message", "A reviewer will look at your case. The interview cannot start until then."))
    elif s == "HUMAN_REVIEW":
        C.callout("warning", "Waiting for a human reviewer", "Your check could not be confirmed automatically. Please contact the recruiter; the interview stays locked until they respond.")
    elif s == "REJECTED_AT_REVIEW":
        C.callout("error", "Application closed", "Your identity could not be confirmed. Contact the recruiter if you think this is a mistake.")
    elif s in ("IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS") or H.candidate_steps(s)[2][1] == "done":
        C.callout("success", "Identity already confirmed", "Nothing more to do here.")
    else:
        C.callout("info", "Not available yet", "Identity verification opens once your interview is scheduled.")


def join_interview(info):
    C.page_header("Join Interview", "Answer by voice or by typing. Take your time.", info["job_title"] or "Candidate workspace")
    s = info["status"]
    if s == "IDENTITY_PASSED":
        with st.container(border=True):
            st.markdown("### Ready to Begin Your Interview")
            st.markdown(
                f"You have satisfied identity verification requirements for **{info['job_title']}**. "
                f"This adaptive interview covers up to **{info['max_questions']} questions**. "
                "You can answer each question using your voice or by typing. Both formats are evaluated identically on substance."
            )
            col_start, _ = st.columns([1.5, 3])
            with col_start:
                if st.button("Start Interview Now", type="primary", use_container_width=True):
                    with st.spinner("Initializing your interview session..."):
                        ok, r = api.request("POST", "/portal/interview/start", token=token())
                    if ok:
                        st.rerun()
                    else:
                        C.callout("error", "Could not start interview", r)
    elif s == "INTERVIEW_IN_PROGRESS":
        room(info)
    elif s == "SCHEDULED":
        C.callout("info", "Verify your identity first", "The interview is locked until your identity check passes. This is enforced by the system, not just this screen.")
        st.button("Go to Identity Verification", on_click=api.go, args=("Identity Verification", "candidate"))
    elif s == "HUMAN_REVIEW":
        C.callout("warning", "Interview locked", "Your identity check is with a human reviewer. Contact the recruiter.")
    elif s in ("INTERVIEW_COMPLETE", "ASSESSED", "DECIDED", "ASSESSMENT_FAILED"):
        with st.container(border=True):
            st.markdown("### Interview Completed 🎉")
            st.markdown(
                "Thank you for completing your interview session! All your answers have been recorded. "
                "Our competency assessment agent is analyzing your responses against job competencies. "
                "You can view your detailed feedback and development insights on the feedback page."
            )
            col_fb, _ = st.columns([1.5, 3])
            with col_fb:
                st.button("View My Feedback", on_click=api.go, args=("My Feedback", "candidate"), type="primary", use_container_width=True)
    else:
        C.callout("info", "Not available yet", "You will be able to join once your interview is scheduled and your identity is verified.")


def room(info):
    ok, st_ = api.request("GET", "/portal/interview/state", token=token())
    if not ok or not st_.get("started"):
        C.callout("error", "Could not load the interview", st_ if not ok else "No interview session found.")
        return
    if st_["status"] == "SUSPENDED":
        C.callout("warning", "Interview paused", "A human identity review is in progress. You will be able to continue once it is resolved.")
        return

    # Accurate progress calculation (never prematurely 100%)
    transcript = st_.get("transcript", [])
    completed_answers = len([t for t in transcript if t.get("role") == "candidate"])
    max_q = max(int(st_.get("max_questions", 8)), 1)
    is_concluded = st_.get("status") == "CONCLUDED"

    n = completed_answers + 1
    if is_concluded:
        progress_val = 1.0
        progress_txt = f"Interview completed ({completed_answers} questions answered)"
    else:
        # Progress reflects completed candidate responses out of max possible questions
        progress_val = min(0.95, completed_answers / max_q)
        progress_txt = f"Question {min(n, max_q)} of up to {max_q} ({int((completed_answers / max_q) * 100)}% completed)"

    C.badges(
        C.badge(info["job_title"] or "Interview", "neutral", dot=False),
        C.badge(info["name"] or "Candidate", "neutral", dot=False),
        C.badge(f"Question {min(n, max_q)} of max {max_q}", "info", dot=False)
    )
    st.progress(progress_val, text=progress_txt)

    # Optional conversation history expander (keeps one question focused)
    history = [t for t in transcript[:-1] if t.get("text")]
    if history:
        with st.expander(f"Review previous questions and your answers ({len(history)} entries)", expanded=False):
            for t in history:
                with st.chat_message("assistant" if t["role"] == "interviewer" else "user"):
                    st.write(t["text"])

    # Focused Single Question Card
    q = st_["question"]
    C.question_card("Current Interview Question", q)

    # Answering modes: Voice and Text
    tab_voice, tab_text = st.tabs(["🎙️ Voice Answering", "⌨️ Direct Typing"])
    with tab_voice:
        st.caption("Click 'Start speaking' below. When finished speaking, click 'Done speaking' to copy your transcript to the answer box.")
        v = voice(question=q, nonce=str(n), autospeak=True, key=f"voice{n}", default=None)
        if v and v.get("ts") != st.session_state.get(f"last_ts_{n}"):
            st.session_state[f"last_ts_{n}"] = v["ts"]
            current_typed = st.session_state.get(f"ans{n}", "")
            # If candidate already typed something, append; otherwise set
            if current_typed and current_typed.strip() not in v["transcript"]:
                st.session_state[f"ans{n}"] = current_typed.strip() + " " + v["transcript"].strip()
            else:
                st.session_state[f"ans{n}"] = v["transcript"].strip()
    with tab_text:
        st.caption("You can type your full answer directly, or paste text here.")

    # Editable textarea for the final answer
    st.markdown("**Your Answer** *(You can edit and refine the text below before submitting)*:")
    ans = st.text_area(
        "Candidate Answer",
        key=f"ans{n}",
        height=160,
        placeholder="Speak using the voice tool above or type your answer here. Provide specific real-world examples with outcomes...",
        label_visibility="collapsed"
    )

    # Prevent accidental duplicate submissions
    is_submitting = st.session_state.get(f"submitting_{n}", False)
    col_sub, _ = st.columns([1.5, 3])
    with col_sub:
        btn_disabled = not (ans or "").strip() or is_submitting
        if st.button("Submit Answer", type="primary", disabled=btn_disabled, use_container_width=True, key=f"btn_sub_{n}"):
            st.session_state[f"submitting_{n}"] = True
            with st.spinner("The interviewer is evaluating your answer and preparing the next turn..."):
                ok, r = api.request("POST", "/portal/interview/answer", token=token(), json={"answer": ans.strip()})
            st.session_state[f"submitting_{n}"] = False
            if ok:
                st.rerun()
            else:
                C.callout("error", "Your answer was not accepted", r)

    # Mid-session periodic verification check
    with st.expander("Periodic Identity Re-check (Optional)"):
        st.caption("If requested by the recruiter to re-verify during the session, capture a photo here.")
        sc = None
        if info["identity_is_demo"]:
            sc = st.selectbox("Simulated outcome (demo adapter)", info["demo_identity_scenarios"] or ["match"], key=f"midsc_{n}")
        shot = st.camera_input("Re-check photo", key=f"mid_{n}")
        if st.button("Submit Re-check", key=f"btn_recheck_{n}"):
            files = {"frame": ("frame.jpg", shot.getvalue())} if shot else None
            ok, r = api.request("POST", "/portal/identity-check", token=token(), files=files, data={"scenario": sc or "", "check_type": "mid_session"})
            if not ok:
                C.callout("error", "Re-check could not run", r)
            elif r.get("passed"):
                C.callout("success", "Identity re-check passed")
            else:
                st.rerun()


def feedback(info):
    C.page_header("My Feedback", "Based only on the answers you gave in this interview.", info["job_title"] or "Candidate workspace")
    ok, fb = api.request("GET", "/portal/feedback", token=token())
    if not ok:
        C.callout("error", "Could not load feedback", fb)
        return

    if not fb.get("available"):
        s = info.get("status")
        if s in ("INTERVIEW_COMPLETE", "ASSESSMENT_FAILED"):
            C.callout(
                "info",
                "Interview Completed - Assessment Finalization",
                fb.get("message", "Your interview has ended and your responses are being analyzed. Click below to retrieve your feedback.")
            )
            col_ref, _ = st.columns([1.5, 3])
            with col_ref:
                if st.button("Refresh / Finalize Feedback", type="primary", use_container_width=True):
                    with st.spinner("Finalizing your competency feedback..."):
                        api.request("POST", "/portal/interview/retry-assessment", token=token())
                    st.rerun()
        else:
            C.empty_state(
                "Feedback Not Ready Yet",
                fb.get("message", "Complete your scheduled interview session and your feedback will appear here."),
                icon="📝"
            )
        return

    with st.container(border=True):
        st.markdown("#### Overall Summary")
        st.write(fb.get("summary", "Assessment completed."))

    a, b = st.columns(2, gap="large")
    with a:
        C.section("What went well")
        for x in fb.get("strengths", []):
            st.markdown(f"- {x}")
    with b:
        C.section("Where to improve")
        for x in fb.get("weaknesses", []):
            st.markdown(f"- {x}")

    imp = fb.get("improvement_areas", [])
    if imp:
        C.section("What to practise next", "Specific suggestions from the assessment.")
        for x in imp:
            st.markdown(f"- {x}")

    comps = fb.get("competencies", [])
    if comps:
        C.section("Topic by topic", "How your answers read for each topic, with your own words as evidence.")
        tone = {"Strong evidence": "success", "Developing": "warning", "Needs more evidence": "error"}
        for comp in comps:
            with st.expander(comp["name"]):
                lvl = comp.get("level", "Developing")
                C.badges(C.badge(lvl, tone.get(lvl, "neutral")))
                evidence = comp.get("evidence", [])
                if evidence:
                    st.caption("From your answers:")
                    for e in evidence:
                        C.quote(e)
                else:
                    st.caption("Your answers did not include a specific example for this topic. Adding one would strengthen it.")

    note = fb.get("note", "This feedback reflects only your answers in this interview. A human recruiter makes all hiring decisions.")
    st.caption(note)
