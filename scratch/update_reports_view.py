with open('frontend/iqui/views/reports.py', 'r', encoding='utf-8') as f:
    c = f.read()

old_metrics = '''    # 1. Scores Grid
    C.metric_grid([
        {"label": f"Resume Score ({w_res * 100:.0f}%)", "value": f"{resume_score:.1f}", "hint": f"Rank #{rep['resume']['rank'] or '-'} · Out of 100"},
        {"label": f"Interview Score ({w_int * 100:.0f}%)", "value": "Pending", "hint": "Awaiting interview session"},
        {"label": "Final Weighted Score", "value": "Pending", "hint": f"Calculated after interview assessment"},
    ])'''

new_metrics = '''    # 1. Scores Grid
    int_score_val = "Pending"
    int_score_hint = "Awaiting interview session"
    if rep["status"] == "INTERVIEW_COMPLETE":
        int_score_val = "Ready"
        int_score_hint = "Ready for assessment generation"
    elif rep["status"] == "ASSESSMENT_FAILED":
        int_score_val = "Failed"
        int_score_hint = "Assessment failed - retry available"

    C.metric_grid([
        {"label": f"Resume Score ({w_res * 100:.0f}%)", "value": f"{resume_score:.1f}", "hint": f"Rank #{rep['resume']['rank'] or '-'} · Out of 100"},
        {"label": f"Interview Score ({w_int * 100:.0f}%)", "value": int_score_val, "hint": int_score_hint},
        {"label": "Final Weighted Score", "value": "Pending", "hint": "Calculated after interview assessment"},
    ])'''

old_status_map = '''        "INTERVIEW_IN_PROGRESS": "The interview session is currently in progress.",
        "REJECTED_AT_REVIEW": "Application was closed at identity review stage.",
    }
    explanation = status_messages.get(rep["status"], "Interview assessment has not been completed yet.")
    C.callout("info", "No Interview Assessment Yet", explanation)'''

new_status_map = '''        "INTERVIEW_IN_PROGRESS": "The interview session is currently in progress.",
        "INTERVIEW_COMPLETE": "The candidate has completed their interview session. Click 'Generate Assessment' below to evaluate answers against competency rubrics.",
        "ASSESSMENT_FAILED": "Interview was completed, but automated assessment generation encountered an error. Click 'Retry Assessment' below to re-evaluate.",
        "REJECTED_AT_REVIEW": "Application was closed at identity review stage.",
    }
    explanation = status_messages.get(rep["status"], "Interview assessment has not been completed yet.")
    callout_tone = "error" if rep["status"] == "ASSESSMENT_FAILED" else ("warning" if rep["status"] == "INTERVIEW_COMPLETE" else "info")
    callout_title = "Assessment Generation Required" if rep["status"] in ("INTERVIEW_COMPLETE", "ASSESSMENT_FAILED") else "No Interview Assessment Yet"
    C.callout(callout_tone, callout_title, explanation)'''

old_actions = '''    # 4. Interactive Action: Conduct Interview & Generate Assessment
    if rep["status"] in ("SCHEDULED", "IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS"):
        with st.container(border=True):
            st.markdown("#### Advance Candidate Workflow")
            st.write("Progress this candidate through identity verification, conduct the interview session, and generate the competency assessment report.")
            col_act, _ = st.columns([2, 3])
            with col_act:
                if st.button("Conduct Interview & Generate Assessment", type="primary", use_container_width=True, key=f"btn_cond_{app_id}"):
                    with st.spinner("Conducting interview session and generating assessment..."):
                        res = api.call("POST", f"/applications/{app_id}/conduct-interview")
                        if res:
                            api.flash("success", "Workflow Advanced", "Interview completed and assessment generated successfully.")
                            st.rerun()'''

new_actions = '''    # 4. Interactive Action: Conduct Interview & Generate Assessment
    if rep["status"] in ("SCHEDULED", "IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS"):
        with st.container(border=True):
            st.markdown("#### Advance Candidate Workflow")
            st.write("Progress this candidate through identity verification, conduct the interview session, and generate the competency assessment report.")
            col_act, _ = st.columns([2, 3])
            with col_act:
                if st.button("Conduct Interview & Generate Assessment", type="primary", use_container_width=True, key=f"btn_cond_{app_id}"):
                    with st.spinner("Conducting interview session and generating assessment..."):
                        res = api.call("POST", f"/applications/{app_id}/conduct-interview")
                        if res:
                            api.flash("success", "Workflow Advanced", "Interview completed and assessment generated successfully.")
                            st.rerun()
    elif rep["status"] in ("INTERVIEW_COMPLETE", "ASSESSMENT_FAILED"):
        with st.container(border=True):
            st.markdown("#### Generate Candidate Assessment")
            st.write("The interview session has been recorded. Run the Assessment Agent to score competencies, cite evidence, and compute the final score.")
            col_act, _ = st.columns([2, 3])
            with col_act:
                btn_lbl = "Retry Assessment Generation" if rep["status"] == "ASSESSMENT_FAILED" else "Generate Competency Assessment"
                if st.button(btn_lbl, type="primary", use_container_width=True, key=f"btn_run_asm_{app_id}"):
                    with st.spinner("Evaluating interview responses against job competencies..."):
                        res = api.call("POST", f"/applications/{app_id}/assessment/retry")
                        if res:
                            api.flash("success", "Assessment Completed", "Competency scores and candidate feedback generated successfully.")
                            st.rerun()'''

assert old_metrics in c, 'old_metrics not found'
assert old_status_map in c, 'old_status_map not found'
assert old_actions in c, 'old_actions not found'

c = c.replace(old_metrics, new_metrics).replace(old_status_map, new_status_map).replace(old_actions, new_actions)

with open('frontend/iqui/views/reports.py', 'w', encoding='utf-8') as f:
    f.write(c)
print('Successfully updated frontend/iqui/views/reports.py')
