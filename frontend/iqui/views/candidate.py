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
        C.callout("success", "You are ready", f"The interview has up to {info['max_questions']} questions and adapts to your answers.")
        if st.button("Start interview", type="primary"):
            ok, r = api.request("POST", "/portal/interview/start", token=token())
            if ok:
                st.rerun()
            C.callout("error", "Could not start", r)
    elif s == "INTERVIEW_IN_PROGRESS":
        room(info)
    elif s == "SCHEDULED":
        C.callout("info", "Verify your identity first", "The interview is locked until your identity check passes. This is enforced by the system, not just this screen.")
        st.button("Go to Identity Verification", on_click=api.go, args=("Identity Verification", "candidate"))
    elif s == "HUMAN_REVIEW":
        C.callout("warning", "Interview locked", "Your identity check is with a human reviewer. Contact the recruiter.")
    elif s in ("INTERVIEW_COMPLETE", "ASSESSED", "DECIDED", "ASSESSMENT_FAILED"):
        C.callout("success", "Interview complete", "Thank you for your time.")
        st.button("See my feedback", on_click=api.go, args=("My Feedback", "candidate"), type="primary")
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
    n = st_["questions_asked"]
    C.badges(C.badge(info["job_title"] or "Interview", "neutral", dot=False), C.badge(info["name"] or "Candidate", "neutral", dot=False),
             C.badge(f"Question {n} of up to {st_['max_questions']}", "info", dot=False))
    st.progress(min(1.0, (n - 1) / st_["max_questions"]), text="Progress")
    history = st_["transcript"][:-1]
    if history:
        with st.expander(f"Conversation so far ({len(history)} messages)", expanded=False):
            for t in history:
                with st.chat_message("assistant" if t["role"] == "interviewer" else "user"):
                    st.write(t["text"])
    q = st_["question"]
    C.question_card("Interviewer", q)
    v = voice(question=q, nonce=str(n), autospeak=True, key=f"voice{n}", default=None)
    if v and v.get("ts") != st.session_state.get("last_ts"):
        st.session_state["last_ts"] = v["ts"]
        st.session_state[f"ans{n}"] = v["transcript"]
    st.caption("Voice not working? Use Chrome or Edge and allow the microphone - or simply type your answer below.")
    ans = st.text_area("Your answer", key=f"ans{n}", height=150, placeholder="Speak with the microphone button above, or type here. You can edit a voice transcript before sending.")
    if st.button("Submit answer", type="primary", disabled=not (ans or "").strip()):
        with st.spinner("The interviewer is thinking about your answer..."):
            ok, r = api.request("POST", "/portal/interview/answer", token=token(), json={"answer": ans})
        if ok:
            st.rerun()
        else:
            C.callout("error", "Your answer was not accepted", r)
    with st.expander("Periodic identity re-check"):
        st.caption("If the recruiter asks you to re-verify during the interview, do it here. A failed re-check pauses the interview for human review.")
        sc = None
        if info["identity_is_demo"]:
            sc = st.selectbox("Simulated outcome (demo adapter)", info["demo_identity_scenarios"] or ["match"], key="midsc")
        shot = st.camera_input("Re-check photo", key=f"mid{n}")
        if st.button("Run re-check"):
            files = {"frame": ("frame.jpg", shot.getvalue())} if shot else None
            ok, r = api.request("POST", "/portal/identity-check", token=token(), files=files, data={"scenario": sc or "", "check_type": "mid_session"})
            if not ok:
                C.callout("error", "Re-check could not run", r)
            elif r["passed"]:
                C.callout("success", "Re-check passed")
            else:
                st.rerun()


def feedback(info):
    C.page_header("My Feedback", "Based only on the answers you gave in this interview.", info["job_title"] or "Candidate workspace")
    ok, fb = api.request("GET", "/portal/feedback", token=token())
    if not ok:
        C.callout("error", "Could not load feedback", fb)
        return
    if not fb["available"]:
        C.empty_state("Your feedback is not ready yet", "Finish the interview and it will appear here.")
        return
    with st.container(border=True):
        st.write(fb["summary"])
    a, b = st.columns(2, gap="large")
    with a:
        C.section("What went well")
        for x in fb["strengths"]:
            st.markdown(f"- {x}")
    with b:
        C.section("Where to improve")
        for x in fb["weaknesses"]:
            st.markdown(f"- {x}")
    C.section("What to practise next", "Specific suggestions from the assessment.")
    for x in fb["improvement_areas"]:
        st.markdown(f"- {x}")
    if fb["competencies"]:
        C.section("Topic by topic", "How your answers read for each topic, with your own words as evidence.")
        tone = {"Strong evidence": "success", "Developing": "warning", "Needs more evidence": "error"}
        for c in fb["competencies"]:
            with st.expander(c["name"]):
                C.badges(C.badge(c["level"], tone.get(c["level"], "neutral")))
                if c["evidence"]:
                    st.caption("From your answers:")
                    for e in c["evidence"]:
                        C.quote(e)
                else:
                    st.caption("Your answers did not include a specific example for this topic. Adding one would strengthen it.")
    st.caption(fb["note"] + " A readiness score is not shown because this system does not calculate one.")
