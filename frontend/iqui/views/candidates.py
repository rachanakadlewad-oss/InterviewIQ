"""Recruiter Candidates Management View.
Displays all candidates who applied to the logged-in recruiter's jobs,
with full search, job and status filtering, sorting, comprehensive AI evaluation breakdown,
extracted resume profiles, and interactive Shortlist / Reject / Review status actions."""
from pathlib import Path
from typing import Any, Dict, List, Optional
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
    job_lookup = {}
    default_job_idx = 0

    active_job_id = st.session_state.get("job_id")
    for idx, j in enumerate(jobs_list):
        label = f"{j['title']} (#{j['id']})"
        job_options[label] = j["id"]
        job_lookup[j["id"]] = j
        if active_job_id and j["id"] == active_job_id:
            default_job_idx = idx + 1  # +1 because "All Jobs" is at 0

    # 2. Search, Filter & Sort Controls
    with st.container(border=True):
        c_search, c_job, c_status, c_sort = st.columns([1.8, 1.6, 1.4, 1.4], vertical_alignment="bottom")
        with c_search:
            search_query = st.text_input("🔍 Search Candidates", placeholder="Name, email, or skill...", key="cand_search_input")
        with c_job:
            selected_job_label = st.selectbox(
                "Filter by Job",
                list(job_options.keys()),
                index=default_job_idx if default_job_idx < len(job_options) else 0,
                key="cand_job_filter"
            )
            selected_job_id = job_options[selected_job_label]
            if selected_job_id:
                st.session_state["job_id"] = selected_job_id
        with c_status:
            status_filter = st.selectbox(
                "Filter by Status",
                [
                    "Active Candidates",
                    "Pending Review",
                    "Shortlisted",
                    "Accepted",
                    "Scheduled",
                    "Rejected / Archived",
                    "All (including Rejected)"
                ],
                index=0,
                key="cand_status_filter"
            )
        with c_sort:
            sort_by = st.selectbox(
                "Sort by",
                ["AI Score (High to Low)", "Date (Newest First)", "Name (A-Z)"],
                key="cand_sort_by"
            )

    # Map frontend filter selection to API status parameter
    status_api_param = None
    if status_filter == "Active Candidates":
        status_api_param = "ACTIVE"
    elif status_filter == "Shortlisted":
        status_api_param = "SHORTLISTED"
    elif status_filter == "Pending Review":
        status_api_param = "PENDING_REVIEW"
    elif status_filter == "Accepted":
        status_api_param = "ACCEPTED"
    elif status_filter == "Scheduled":
        status_api_param = "SCHEDULED"
    elif status_filter == "Rejected / Archived":
        status_api_param = "REJECTED"
    elif status_filter == "All (including Rejected)":
        status_api_param = "ALL"

    # 3. Fetch candidate counts and list from database
    counts = api.get_candidate_counts(job_id=selected_job_id)
    candidates_data = api.get_recruiter_candidates(
        job_id=selected_job_id,
        status=status_api_param,
        search=search_query.strip() if search_query else None
    )

    # Sort candidates in frontend
    if sort_by == "AI Score (High to Low)":
        candidates_data.sort(key=lambda c: (c.get("ai_score") if c.get("ai_score") is not None else (c.get("resume_score") or 0.0)), reverse=True)
    elif sort_by == "Date (Newest First)":
        candidates_data.sort(key=lambda c: (c.get("created_at") or ""), reverse=True)
    elif sort_by == "Name (A-Z)":
        candidates_data.sort(key=lambda c: (c.get("candidate_name") or c.get("name") or "").lower())

    # Metrics summary header (directly backed by real database counts, never truncated by active search)
    C.html(
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin:0.5rem 0 1rem;flex-wrap:wrap;gap:0.75rem;">'
        f'<div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">'
        f'<span class="iq-badge info" style="font-size:0.84rem;padding:0.25rem 0.75rem;">'
        f'<b>{counts.get("active", 0)}</b> Active Candidates'
        f'</span>'
        f'<span class="iq-badge success" style="font-size:0.84rem;padding:0.25rem 0.75rem;">'
        f'<b>{counts.get("shortlisted", 0)}</b> Shortlisted'
        f'</span>'
        f'<span class="iq-badge warning" style="font-size:0.84rem;padding:0.25rem 0.75rem;">'
        f'<b>{counts.get("pending", 0)}</b> Pending Review'
        f'</span>'
        f'<span class="iq-badge error" style="font-size:0.84rem;padding:0.25rem 0.75rem;">'
        f'<b>{counts.get("rejected", 0)}</b> Rejected / Archived'
        f'</span>'
        f'</div>'
        f'<span style="font-size:0.82rem;color:var(--muted);">All records synced with database</span>'
        f'</div>'
    )

    # 4. Render candidate listing or empty state
    if not candidates_data:
        empty_title = "No Rejected Candidates" if status_filter == "Rejected / Archived" else "No Candidates Found"
        empty_msg = (
            "No candidates are currently marked as rejected for this filter."
            if status_filter == "Rejected / Archived"
            else "No candidate applications matched your search and filter criteria. Adjust your filters or upload new candidate resumes below."
        )
        C.empty_state(empty_title, empty_msg, icon="👥")
    else:
        for cand in candidates_data:
            aid = cand["application_id"]
            cand_name = cand.get("candidate_name") or cand.get("name") or f"Candidate #{aid}"
            cand_email = cand.get("email") or "No email provided"
            job_title = cand.get("job_title") or f"Job #{cand.get('job_id')}"
            status = cand.get("status", "PENDING_REVIEW")
            is_rejected = (status == "REJECTED")
            is_shortlisted = bool((cand.get("shortlisted") or status == "SHORTLISTED") and not is_rejected)
            ai_score = cand.get("ai_score") if cand.get("ai_score") is not None else cand.get("resume_score")

            applied_date = cand.get("created_at") or "-"
            if "T" in applied_date:
                applied_date = applied_date.split("T")[0]
            skills = cand.get("skills") or []
            eval_info = cand.get("ai_reasoning") or {}

            # Score tone, percentage & classification
            score_val = f"{ai_score:.1f}" if ai_score is not None else "Pending"
            score_pct = max(0.0, min(100.0, ai_score or 0.0))
            if ai_score is not None:
                if ai_score >= 75.0:
                    score_tone = "success"
                    match_class = "Strong Match"
                    match_badge = C.badge("Strong Match", "success", dot=True)
                elif ai_score >= 50.0:
                    score_tone = "warning"
                    match_class = "Moderate Match"
                    match_badge = C.badge("Moderate Match", "warning", dot=True)
                else:
                    score_tone = "error"
                    match_class = "Low Match"
                    match_badge = C.badge("Low Match", "error", dot=True)
            else:
                score_tone = "neutral"
                match_class = "Pending Evaluation"
                match_badge = C.badge("Pending Evaluation", "neutral", dot=False)

            # Short suitability summary
            suitability_summary = eval_info.get("recommendation") or ""
            if not suitability_summary and eval_info.get("detailed_explanation"):
                suitability_summary = eval_info["detailed_explanation"][:110].strip() + "..."
            if not suitability_summary:
                suitability_summary = "Candidate profile parsed and ready for technical review."

            # Candidate Card Container
            with st.container(border=True):
                c_left, c_mid, c_right = st.columns([2.5, 2.0, 1.5], vertical_alignment="top")

                # LEFT SECTION: Candidate profile, applied role, dates, skills
                with c_left:
                    status_badge_html = C.status_badge(status)
                    shortlist_badge_html = f" {C.badge('Shortlisted', 'success', dot=False)}" if is_shortlisted else ""
                    
                    skill_badges_html = ""
                    if skills:
                        skill_badges_html = "".join(
                            f'<span class="iq-badge neutral" style="font-size:0.72rem;padding:0.12rem 0.45rem;margin:0.12rem 0.2rem 0.12rem 0;">{C.esc(s)}</span>'
                            for s in skills[:6]
                        )
                        if len(skills) > 6:
                            skill_badges_html += f'<span class="iq-badge neutral" style="font-size:0.72rem;padding:0.12rem 0.45rem;">+{len(skills)-6} more</span>'

                    C.html(
                        f'<div>'
                        f'<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.25rem;">'
                        f'<span style="font-size:1.15rem;font-weight:750;color:var(--text);letter-spacing:-0.01em;">{C.esc(cand_name)}</span>'
                        f'{status_badge_html}'
                        f'{shortlist_badge_html}'
                        f'</div>'
                        f'<div style="font-size:0.86rem;color:var(--text2);margin-bottom:0.25rem;">'
                        f'Role: <b style="color:var(--text);">{C.esc(job_title)}</b> &nbsp;·&nbsp; {C.esc(cand_email)}'
                        f'</div>'
                        f'<div style="font-size:0.78rem;color:var(--muted);margin-bottom:0.4rem;">'
                        f'Applied: {C.esc(applied_date)} &nbsp;·&nbsp; Ref ID: #{aid}'
                        f'</div>'
                        f'<div style="display:flex;align-items:center;flex-wrap:wrap;margin-top:0.25rem;">'
                        f'{skill_badges_html}'
                        f'</div>'
                        f'</div>'
                    )

                # MIDDLE SECTION: AI matching score, progress bar, match classification, suitability summary
                with c_mid:
                    C.html(
                        f'<div style="padding:0 0.5rem;">'
                        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.2rem;">'
                        f'<span style="font-size:0.72rem;text-transform:uppercase;color:var(--muted);font-weight:700;letter-spacing:0.05em;">AI Match Score</span>'
                        f'{match_badge}'
                        f'</div>'
                        f'<div style="display:flex;align-items:baseline;gap:0.35rem;margin:0.1rem 0;">'
                        f'<span style="font-size:1.65rem;font-weight:800;color:var(--text);line-height:1.1;">{score_val}</span>'
                        f'<span style="font-size:0.85rem;color:var(--muted);font-weight:500;">/ 100</span>'
                        f'</div>'
                        f'<div class="iq-bar" style="width:100%;margin:0.25rem 0 0.4rem 0;">'
                        f'<div class="track"><div class="fill {score_tone}" style="width:{score_pct:.0f}%;"></div></div>'
                        f'</div>'
                        f'<div style="font-size:0.80rem;color:var(--text2);line-height:1.4;background:rgba(255,255,255,0.03);padding:0.35rem 0.55rem;border-radius:4px;border-left:2px solid var(--border-light);">'
                        f'{C.esc(suitability_summary)}'
                        f'</div>'
                        f'</div>'
                    )

                # RIGHT SECTION: Action buttons (Shortlist, Reject, Review Details)
                with c_right:
                    details_key = f"show_details_{aid}"
                    is_expanded = st.session_state.get(details_key, False)

                    if not is_rejected:
                        # 1. Shortlist / Un-shortlist Button
                        if not is_shortlisted:
                            if st.button("✅ Shortlist", key=f"btn_sl_{aid}", type="primary", use_container_width=True):
                                api.update_candidate_status(aid, "SHORTLIST")
                                st.rerun()
                        else:
                            if st.button("↩️ Un-shortlist", key=f"btn_unsl_{aid}", use_container_width=True):
                                api.update_candidate_status(aid, "PENDING")
                                st.rerun()

                        # 2. Reject Button (Removes candidate from active listings immediately)
                        if st.button("❌ Reject", key=f"btn_rej_{aid}", use_container_width=True):
                            api.update_candidate_status(aid, "REJECT")
                            st.rerun()
                    else:
                        # For Rejected Candidates: Option to restore
                        if st.button("♻️ Restore to Review", key=f"btn_rest_{aid}", type="primary", use_container_width=True):
                            api.update_candidate_status(aid, "PENDING")
                            st.rerun()

                    # 3. Review Details Button (Toggles candidate breakdown panel)
                    rev_label = "🔼 Close Review" if is_expanded else "📋 Review Details"
                    if st.button(rev_label, key=f"btn_rev_{aid}", use_container_width=True):
                        st.session_state[details_key] = not is_expanded
                        st.rerun()

                # DETAILED AI EVALUATION & RESUME BREAKDOWN PANEL
                if is_expanded:
                    render_candidate_evaluation_breakdown(cand, eval_info, job_lookup)

    # 5. Resume Upload Section for adding new candidates
    st.markdown("<div style='height: 1.2rem;'></div>", unsafe_allow_html=True)
    with st.expander("📤 Upload New Candidate Resumes", expanded=False):
        C.section(
            "Add Resumes to Pipeline",
            "Upload PDF, DOCX, or TXT resumes. AI automatically extracts candidate information, scores qualifications against the selected job description, and queues candidates for review."
        )

        upload_job_options = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs_list}
        if upload_job_options:
            up_job_keys = list(upload_job_options.keys())
            up_default_idx = 0
            if selected_job_id:
                for k_idx, k in enumerate(up_job_keys):
                    if upload_job_options[k] == selected_job_id:
                        up_default_idx = k_idx
                        break

            target_upload_label = st.selectbox("Select Target Job Opening *", up_job_keys, index=up_default_idx, key="up_target_job_select")
            target_upload_job = upload_job_options[target_upload_label]

            files = st.file_uploader(
                "Select one or multiple resume files (PDF, DOCX, TXT)",
                accept_multiple_files=True,
                type=["pdf", "docx", "txt"],
                key="admin_resume_uploader"
            )

            if st.button("🚀 Parse & Score Resumes", type="primary", disabled=not files, use_container_width=True):
                bar = st.progress(0.0, text="Uploading, extracting text, and running AI evaluation...")
                success_count = 0
                error_messages = []

                for i, f in enumerate(files):
                    parts = {"file": (f.name, f.getvalue())}
                    ok, data = api.request("POST", f"/jobs/{target_upload_job}/applications", files=parts)
                    if ok:
                        success_count += 1
                    else:
                        error_messages.append(f"**{f.name}**: {data}")
                    bar.progress((i + 1) / len(files), text=f"Processed {i + 1} of {len(files)} resume(s)...")

                bar.empty()

                if success_count > 0:
                    api.flash(
                        "success",
                        "Resumes Processed Successfully",
                        f"Successfully parsed and evaluated {success_count} candidate resume(s) for '{target_upload_label}'. Scores and summaries are ready below."
                    )
                if error_messages:
                    api.flash(
                        "error" if success_count == 0 else "warning",
                        "Upload Notice",
                        "Issues encountered with some files:<br>" + "<br>".join(error_messages)
                    )
                st.rerun()
        else:
            C.empty_state("No Job Openings Configured", "Please create a job opening in the Jobs section before uploading resumes.", icon="💼")


def render_candidate_evaluation_breakdown(cand: Dict[str, Any], eval_info: Dict[str, Any], job_lookup: Dict[int, Any]):
    """Renders the comprehensive, high-contrast AI evaluation breakdown and extracted resume details (Section 5)."""
    aid = cand["application_id"]
    cand_name = cand.get("candidate_name") or cand.get("name") or f"Candidate #{aid}"
    job_id = cand.get("job_id")
    job = job_lookup.get(job_id) or {}
    job_title = job.get("title") or cand.get("job_title") or f"Job #{job_id}"
    company = job.get("company") or cand.get("company") or "TechCorp"
    ai_score = cand.get("ai_score") if cand.get("ai_score") is not None else cand.get("resume_score")
    scoring_src = cand.get("scoring_source", "semantic_rules")
    scoring_src_label = "Live Generative LLM" if scoring_src == "llm" else "Calibrated Semantic Analysis"

    st.markdown("<hr style='margin:0.8rem 0;'>", unsafe_allow_html=True)
    st.markdown(f"### 📋 Candidate Details & AI Evaluation for {cand_name}")
    st.caption(f"Evaluated against: **{job_title}** at **{company}** | Engine: **{scoring_src_label}**")

    # A. Overall Match Score & Classification Banner
    overall_score = eval_info.get("overall_score", ai_score or 0.0)
    score_tone = "success" if overall_score >= 75.0 else ("warning" if overall_score >= 50.0 else "error")
    match_classification = "Strong Match" if overall_score >= 75.0 else ("Moderate Match" if overall_score >= 50.0 else "Low Match")

    C.html(
        f'<div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:1rem 1.25rem;margin-bottom:1rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem;">'
        f'<div>'
        f'<div style="font-size:0.75rem;text-transform:uppercase;color:var(--muted);font-weight:700;letter-spacing:0.06em;">Overall Candidate-Job Match</div>'
        f'<div style="display:flex;align-items:baseline;gap:0.4rem;margin:0.2rem 0;">'
        f'<span style="font-size:2.2rem;font-weight:800;color:var(--text);line-height:1;">{overall_score:.1f}</span>'
        f'<span style="font-size:0.95rem;color:var(--muted);font-weight:600;">/ 100</span>'
        f'</div>'
        f'<div class="iq-bar" style="width:240px;margin-top:0.3rem;">'
        f'<div class="track"><div class="fill {score_tone}" style="width:{overall_score:.0f}%;"></div></div>'
        f'</div>'
        f'</div>'
        f'<div style="display:flex;flex-direction:column;align-items:flex-end;gap:0.4rem;">'
        f'{C.badge(match_classification, score_tone, dot=True)}'
        f'{C.badge(scoring_src_label, "info" if scoring_src == "llm" else "warning", dot=False)}'
        f'<span style="font-size:0.75rem;color:var(--muted);">Role: {C.esc(job_title)}</span>'
        f'</div>'
        f'</div>'
    )

    # B. Four Evaluation Categories
    tech_data = eval_info.get("technical_skills_match", {})
    exp_data = eval_info.get("experience_relevance", {})
    proj_data = eval_info.get("project_relevance", {})
    edu_data = eval_info.get("educational_relevance", {})

    t_score = tech_data.get("score", overall_score)
    e_score = exp_data.get("score", overall_score)
    p_score = proj_data.get("score", overall_score)
    edu_score = edu_data.get("score", 85.0 if cand.get("education") else 70.0)

    cat_col1, cat_col2, cat_col3, cat_col4 = st.columns(4)

    with cat_col1:
        with st.container(border=True):
            st.markdown(f"**🛠️ Technical Skills**")
            st.markdown(f"### `{t_score:.1f}%`")
            st.progress(max(0.0, min(1.0, t_score / 100.0)))
            st.caption(tech_data.get("assessment", "Direct competency alignment against required skills."))

    with cat_col2:
        with st.container(border=True):
            st.markdown(f"**💼 Experience Relevance**")
            st.markdown(f"### `{e_score:.1f}%`")
            st.progress(max(0.0, min(1.0, e_score / 100.0)))
            st.caption(exp_data.get("assessment", "Seniority and professional history alignment with role."))

    with cat_col3:
        with st.container(border=True):
            st.markdown(f"**🚀 Project Deliverables**")
            st.markdown(f"### `{p_score:.1f}%`")
            st.progress(max(0.0, min(1.0, p_score / 100.0)))
            st.caption(proj_data.get("assessment", "Verifiable engineering contributions and implementations."))

    with cat_col4:
        with st.container(border=True):
            st.markdown(f"**🎓 Educational Relevance**")
            st.markdown(f"### `{edu_score:.1f}%`")
            st.progress(max(0.0, min(1.0, edu_score / 100.0)))
            st.caption(edu_data.get("assessment", "Academic qualifications and technical foundations."))

    # C & D. Key Strengths vs Areas to Verify / Gaps
    col_str, col_gap = st.columns(2)
    with col_str:
        with st.container(border=True):
            st.markdown("#### 🌟 Key Strengths & Proven Competencies")
            strengths = eval_info.get("strengths") or []
            if strengths:
                for s_item in strengths:
                    st.markdown(f"✅ **{s_item}**")
            else:
                st.info("Foundational exposure to core responsibilities of this position.")

    with col_gap:
        with st.container(border=True):
            st.markdown("#### ⚠️ Areas to Verify / Skill Gaps")
            gaps = eval_info.get("missing_or_weak_requirements") or []
            if gaps:
                for g_item in gaps:
                    st.markdown(f"🔍 **{g_item}**")
            else:
                st.info("No critical skill gaps identified; verify depth during technical interview.")

    # E. Detailed AI Assessment
    detailed_exp = eval_info.get("detailed_explanation")
    rec_note = eval_info.get("recommendation")
    if detailed_exp or rec_note:
        with st.container(border=True):
            st.markdown("#### 🧠 Detailed AI Assessment Explanation")
            if detailed_exp:
                st.markdown(detailed_exp)
            if rec_note:
                st.markdown(f"**Recruiter Recommendation:** `{rec_note}`")

    # F. Extracted Resume Information
    st.markdown("#### 📄 Extracted Resume Information")
    tab_exp, tab_edu, tab_skills, tab_proj, tab_raw = st.tabs([
        "💼 Experience",
        "🎓 Education",
        "🛠️ Skills",
        "🚀 Projects",
        "📑 Raw Resume Text"
    ])

    with tab_exp:
        exp_list = cand.get("experience") or []
        exp_years = cand.get("experience_years", 0)
        st.markdown(f"**Total Professional Experience:** `{exp_years:.1f} years`")
        if exp_list:
            for item in exp_list:
                st.markdown(f"- {item}")
        else:
            st.caption("No structured role items extracted from text.")

    with tab_edu:
        edu_list = cand.get("education") or []
        if edu_list:
            for item in edu_list:
                st.markdown(f"- 🎓 {item}")
        else:
            st.caption("No specific degree qualifications listed.")

    with tab_skills:
        all_skills = cand.get("skills") or []
        if all_skills:
            st.markdown(" ".join(f"`{s}`" for s in all_skills))
        else:
            st.caption("No technical skills tagged.")

    with tab_proj:
        proj_list = cand.get("projects") or []
        if proj_list:
            for p in proj_list:
                st.markdown(f"- 🚀 **{p}**")
        else:
            st.caption("No dedicated project items extracted.")

    with tab_raw:
        raw_text = cand.get("resume_text") or ""
        if raw_text:
            st.text_area(f"Full text ({cand.get('resume_filename', 'resume')})", raw_text, height=200, key=f"raw_resume_{aid}", disabled=True)
        else:
            st.caption("No raw text available.")

    # Re-evaluate candidate button
    c_btn1, _ = st.columns([2, 3])
    with c_btn1:
        if st.button(f"🔄 Re-evaluate Candidate #{aid} with Active LLM", key=f"btn_rescore_{aid}"):
            with st.spinner(f"Re-evaluating {cand_name} against {job_title}..."):
                api.rescore_candidate(aid)
                api.flash("success", "Evaluation Updated", f"Candidate #{aid} ({cand_name}) has been re-evaluated against '{job_title}'.")
                st.rerun()
