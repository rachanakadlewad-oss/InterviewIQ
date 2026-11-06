"""Recruiter Candidates Management View.
Displays all candidates who applied to the logged-in recruiter's jobs,
with full search, job and status filtering, sorting, LLM evaluation details,
and interactive Shortlist / Reject / Pending status mutation actions."""
from pathlib import Path
import streamlit as st

from .. import api, components as C, helpers as H


def render():
    C.page_header(
        "Candidates",
        "Search, evaluate, and manage candidate applications, AI matching scores, and interview shortlists.",
        "Recruiter workspace"
    )

    # 1. Fetch available jobs for filtering
    jobs_list = api.call("GET", "/jobs") or []
    job_options = {"All Jobs": None}
    for j in jobs_list:
        job_options[f"{j['title']} (#{j['id']})"] = j["id"]

    # 2. Search, Filter & Sort Controls
    with st.container(border=True):
        c_search, c_job, c_status, c_sort = st.columns([1.8, 1.6, 1.3, 1.4])
        with c_search:
            search_query = st.text_input("🔍 Search Candidates", placeholder="Name, email, or skill...", key="cand_search_input")
        with c_job:
            selected_job_label = st.selectbox("Filter by Job", list(job_options.keys()), key="cand_job_filter")
            selected_job_id = job_options[selected_job_label]
        with c_status:
            status_filter = st.selectbox(
                "Filter by Status",
                ["All", "Shortlisted", "Pending / Under Review", "Scheduled", "Decided", "Rejected"],
                key="cand_status_filter"
            )
        with c_sort:
            sort_by = st.selectbox(
                "Sort by",
                ["AI Score (High to Low)", "Date (Newest First)", "Name (A-Z)"],
                key="cand_sort_by"
            )

    # 3. Query candidates from database
    status_api_param = None
    if status_filter == "Shortlisted":
        status_api_param = "SHORTLISTED"
    elif status_filter == "Pending / Under Review":
        status_api_param = "PENDING"
    elif status_filter == "Scheduled":
        status_api_param = "SCHEDULED"
    elif status_filter == "Decided":
        status_api_param = "DECIDED"
    elif status_filter == "Rejected":
        status_api_param = "REJECTED"

    candidates_data = api.get_recruiter_candidates(
        job_id=selected_job_id,
        status=status_api_param,
        search=search_query.strip() if search_query else None
    )

    # Sort candidates in frontend
    if sort_by == "AI Score (High to Low)":
        candidates_data.sort(key=lambda c: (c.get("ai_score") or c.get("resume_score") or 0.0), reverse=True)
    elif sort_by == "Date (Newest First)":
        candidates_data.sort(key=lambda c: (c.get("created_at") or ""), reverse=True)
    elif sort_by == "Name (A-Z)":
        candidates_data.sort(key=lambda c: (c.get("candidate_name") or c.get("name") or "").lower())

    # Metrics summary header
    shortlisted_count = sum(1 for c in candidates_data if c.get("shortlisted") or c.get("status") == "SHORTLISTED")
    pending_count = sum(1 for c in candidates_data if c.get("status") in ("PARSED", "SCORED", "UNDER_REVIEW", "PENDING", "APPLIED") and not c.get("shortlisted"))

    st.markdown(
        f'''<div style="display:flex;align-items:center;justify-content:space-between;margin:0.5rem 0 1rem;flex-wrap:wrap;gap:0.75rem;">
            <div style="display:flex;align-items:center;gap:0.75rem;">
                <span class="iq-badge info" style="font-size:0.85rem;padding:0.25rem 0.75rem;">
                    <b>{len(candidates_data)}</b> Total Candidates Found
                </span>
                <span class="iq-badge success" style="font-size:0.85rem;padding:0.25rem 0.75rem;">
                    <b>{shortlisted_count}</b> Shortlisted
                </span>
                <span class="iq-badge warning" style="font-size:0.85rem;padding:0.25rem 0.75rem;">
                    <b>{pending_count}</b> Pending Review
                </span>
            </div>
            <span style="font-size:0.85rem;color:var(--muted);">All records synced with database</span>
        </div>''',
        unsafe_allow_html=True
    )

    if not candidates_data:
        C.empty_state(
            "No Candidates Found",
            "No applications matched your search and filter criteria. Try adjusting the filters or upload new candidate resumes below.",
            icon="👥"
        )
    else:
        # 4. Render candidate list
        for cand in candidates_data:
            aid = cand["application_id"]
            cand_name = cand.get("candidate_name") or cand.get("name") or f"Candidate #{aid}"
            cand_email = cand.get("email") or "No email provided"
            job_title = cand.get("job_title") or f"Job #{cand.get('job_id')}"
            status = cand.get("status", "APPLIED")
            is_shortlisted = bool(cand.get("shortlisted") or status == "SHORTLISTED")
            ai_score = cand.get("ai_score") if cand.get("ai_score") is not None else cand.get("resume_score")
            applied_date = cand.get("created_at") or "-"
            if "T" in applied_date:
                applied_date = applied_date.split("T")[0]
            skills = cand.get("skills") or []
            eval_info = cand.get("ai_reasoning") or {}

            # Score tone & percentage
            score_val = f"{ai_score:.1f}" if ai_score is not None else "Pending"
            score_pct = max(0.0, min(100.0, ai_score or 0.0))
            score_tone = "success" if (ai_score or 0) >= 70 else ("warning" if (ai_score or 0) >= 45 else "error")

            card_border_class = "is-selected" if is_shortlisted else ""

            with st.container(border=True):
                # Candidate Main Row
                c_info, c_score, c_actions = st.columns([2.6, 1.4, 2.0], vertical_alignment="center")

                with c_info:
                    st.markdown(
                        f'''<div>
                            <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;margin-bottom:0.25rem;">
                                <span style="font-size:1.15rem;font-weight:750;color:var(--text);">{C.esc(cand_name)}</span>
                                {C.status_badge(status)}
                                {C.badge("Shortlisted", "success", dot=False) if is_shortlisted else ""}
                            </div>
                            <div style="font-size:0.86rem;color:var(--text2);margin-bottom:0.25rem;">
                                Role: <b style="color:var(--text);">{C.esc(job_title)}</b> &nbsp;·&nbsp; {C.esc(cand_email)}
                            </div>
                            <div style="font-size:0.78rem;color:var(--muted);">
                                Applied: {C.esc(applied_date)} &nbsp;·&nbsp; Ref ID: #{aid}
                            </div>
                        </div>''',
                        unsafe_allow_html=True
                    )

                with c_score:
                    rec_label = eval_info.get("recommendation", "Evaluation completed")
                    st.markdown(
                        f'''<div style="text-align:center;">
                            <div style="font-size:0.74rem;text-transform:uppercase;color:var(--muted);font-weight:700;letter-spacing:0.05em;">AI Match Score</div>
                            <div style="font-size:1.65rem;font-weight:800;color:var(--text);line-height:1.2;margin:0.15rem 0;">
                                {score_val} <span style="font-size:0.85rem;color:var(--muted);font-weight:500;">/ 100</span>
                            </div>
                            <div class="iq-bar" style="max-width:140px;margin:0 auto 0.2rem auto;">
                                <div class="track"><div class="fill {score_tone}" style="width:{score_pct:.0f}%;"></div></div>
                            </div>
                        </div>''',
                        unsafe_allow_html=True
                    )

                with c_actions:
                    b_col1, b_col2, b_col3 = st.columns(3)
                    with b_col1:
                        if not is_shortlisted:
                            if st.button("✅ Shortlist", key=f"btn_sl_{aid}", type="primary", use_container_width=True):
                                api.update_candidate_status(aid, "SHORTLIST")
                                st.rerun()
                        else:
                            st.caption("✨ Shortlisted")
                    with b_col2:
                        if status != "REJECTED":
                            if st.button("❌ Reject", key=f"btn_rej_{aid}", use_container_width=True):
                                api.update_candidate_status(aid, "REJECT")
                                st.rerun()
                        else:
                            st.caption("Archived")
                    with b_col3:
                        if status not in ("UNDER_REVIEW", "PENDING"):
                            if st.button("⏳ Review", key=f"btn_pend_{aid}", use_container_width=True):
                                api.update_candidate_status(aid, "PENDING")
                                st.rerun()

                # Skills preview row
                if skills:
                    skill_badges = "".join(f'<span class="iq-badge neutral" style="font-size:0.74rem;padding:0.12rem 0.5rem;margin-right:0.35rem;">{C.esc(s)}</span>' for s in skills[:8])
                    st.markdown(f'<div style="margin-top:0.4rem;display:flex;align-items:center;flex-wrap:wrap;gap:0.3rem;">{skill_badges}</div>', unsafe_allow_html=True)

                # Expandable detailed AI evaluation & Resume view
                with st.expander(f"📋 Candidate Details & AI Evaluation for {cand_name}"):
                    if eval_info and isinstance(eval_info, dict) and "technical_skills_match" in eval_info:
                        st.markdown("#### 🧠 AI Candidate-Job Evaluation Breakdown")
                        st.caption(f"Scoring Engine: {cand.get('scoring_source', 'Live LLM').upper()} | Calibrated semantic analysis")

                        # 3-column breakdown: Technical, Experience, Projects
                        c_t, c_e, c_p = st.columns(3)
                        with c_t:
                            tech_m = eval_info.get("technical_skills_match", {})
                            t_score = tech_m.get("score", 0.0)
                            st.markdown(f"**Technical Skills Match: `{t_score:.1f}%`**")
                            st.info(tech_m.get("assessment", "Direct evaluation against required competencies."))
                        with c_e:
                            exp_m = eval_info.get("experience_relevance", {})
                            e_score = exp_m.get("score", 0.0)
                            st.markdown(f"**Experience Relevance: `{e_score:.1f}%`**")
                            st.info(exp_m.get("assessment", "Seniority and role responsibility alignment."))
                        with c_p:
                            proj_m = eval_info.get("project_relevance", {})
                            p_score = proj_m.get("score", 0.0)
                            st.markdown(f"**Project Deliverables: `{p_score:.1f}%`**")
                            st.info(proj_m.get("assessment", "Verifiable engineering contributions."))

                        # Strengths & Gaps
                        col_str, col_gap = st.columns(2)
                        with col_str:
                            st.markdown("**🌟 Key Strengths**")
                            for s_item in eval_info.get("strengths", []):
                                st.markdown(f"- {s_item}")
                        with col_gap:
                            st.markdown("**⚠️ Areas to Verify / Gaps**")
                            for g_item in eval_info.get("missing_or_weak_requirements", []):
                                st.markdown(f"- {g_item}")

                        # Explanation & Recommendation
                        if eval_info.get("detailed_explanation"):
                            st.markdown("**Detailed Assessment Explanation**")
                            C.quote(eval_info["detailed_explanation"])

                        if eval_info.get("recommendation"):
                            st.markdown(f"**Recruiter Recommendation:** `{eval_info['recommendation']}`")

                    else:
                        st.info("Resume parsed. Detailed LLM evaluation will run automatically during screening or rescoring.")

                    # Rescore button
                    if st.button(f"🔄 Re-evaluate Candidate #{aid} with Active LLM", key=f"rescore_btn_{aid}"):
                        with st.spinner("Running AI evaluation..."):
                            api.rescore_candidate(aid)
                            api.flash("success", "Candidate Re-evaluated", f"Updated matching score for {cand_name}.")
                            st.rerun()

                    # Resume Text view
                    resume_text = cand.get("resume_text")
                    if resume_text:
                        st.markdown("---")
                        st.markdown("**📄 Extracted Resume Text**")
                        st.text_area(f"Resume text ({cand.get('resume_filename', 'resume')})", resume_text, height=180, key=f"resume_txt_{aid}", disabled=True)

    # 5. Resume Upload Section for adding new candidates
    st.markdown("<div style='height: 1.2rem;'></div>", unsafe_allow_html=True)
    with st.expander("📤 Upload New Candidate Resumes", expanded=False):
        C.section("Add Resumes to Pipeline", "Upload PDF, DOCX, or TXT files. AI will automatically parse and match candidates to the selected role.")
        target_upload_job = st.selectbox("Select Target Job Opening", [j["id"] for j in jobs_list], format_func=lambda i: next(f"{j['title']} (#{j['id']})" for j in jobs_list if j["id"] == i), key="up_target_job") if jobs_list else None
        
        if target_upload_job:
            files = st.file_uploader("Upload resumes", accept_multiple_files=True, type=["pdf", "docx", "txt"], key="admin_resume_uploader")
            if st.button("Parse & Score Resumes", type="primary", disabled=not files, use_container_width=True):
                bar = st.progress(0.0, text="Uploading and evaluating...")
                success_count = 0
                for i, f in enumerate(files):
                    parts = {"file": (f.name, f.getvalue())}
                    ok, data = api.request("POST", f"/jobs/{target_upload_job}/applications", files=parts)
                    if ok:
                        success_count += 1
                    bar.progress((i + 1) / len(files), text=f"Processed {i + 1} of {len(files)}")
                bar.empty()
                api.flash("success", "Upload Complete", f"Successfully processed {success_count} of {len(files)} resume(s).")
                st.rerun()
        else:
            st.info("Create a job first to upload resumes.")
