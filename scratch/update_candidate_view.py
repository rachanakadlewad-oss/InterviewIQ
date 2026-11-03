with open('frontend/iqui/views/candidate.py', 'r', encoding='utf-8') as f:
    c = f.read()

old_join_to_end = '''def join_interview(info):
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
    st.caption(fb["note"] + " A readiness score is not shown because this system does not calculate one.")'''

new_join_to_end = '''def join_interview(info):
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
                "Interview Completed - Assessment in Progress",
                fb.get("message", "Your interview has ended and your responses are being analyzed. Your personalized feedback will appear here shortly.")
            )
            col_ref, _ = st.columns([1.5, 3])
            with col_ref:
                if st.button("Check Feedback Status", type="primary", use_container_width=True):
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
    st.caption(note)'''

assert old_join_to_end in c, 'old_join_to_end not found'
c = c.replace(old_join_to_end, new_join_to_end)

with open('frontend/iqui/views/candidate.py', 'w', encoding='utf-8') as f:
    f.write(c)
print('Successfully updated frontend/iqui/views/candidate.py')
