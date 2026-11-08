"""InterviewIQ - Modern AI Recruitment Platform.
Run with: streamlit run frontend/streamlit_app.py"""
import streamlit as st

st.set_page_config(
    page_title="InterviewIQ - AI Hiring Platform",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

from iqui import api, components as C  # noqa: E402
from iqui.views import (auth, candidate, candidates, interviews, jobs, overview, reports)  # noqa: E402

# 1. Restore authenticated session across page refreshes
api.restore_session()

RECRUITER_PAGES = {
    "Dashboard": overview.render,
    "Jobs": jobs.render,
    "Candidates": candidates.render,
    "Interviews": interviews.render,
    "Reports": reports.render,
}

RECRUITER_LABELS = {
    "Dashboard": "📊  Dashboard",
    "Jobs": "💼  Jobs",
    "Candidates": "👥  Candidates",
    "Interviews": "🎙️  Interviews",
    "Reports": "📑  Reports",
}

C.inject_theme()
cfg = api.config()

# Handle candidate direct access-token via query params (e.g. ?token=XYZ)
q_token = st.query_params.get("token") or st.query_params.get("access_token")
if q_token and not st.session_state.get("cand_token"):
    st.session_state["cand_token"] = str(q_token)
    st.session_state["role"] = "Candidate"

# Determine role and authenticated user from backend session
current_user = api.get_current_user()
user_role = (current_user.get("role") if current_user else None) or (st.session_state.get("role", "").lower() if st.session_state.get("role") else None)
if not user_role and st.session_state.get("cand_token"):
    user_role = "candidate"


def render_top_corner_profile(user: dict, role: str):
    """Renders small circular avatar containing the first letter of the user's name in top-right corner."""
    name = (user.get("name") if user else None) or ("Recruiter" if role == "recruiter" else "Candidate")
    email = (user.get("email") if user else "") or ""
    first_letter = name.strip()[0].upper() if name.strip() else ("R" if role == "recruiter" else "C")
    first_name = name.split()[0] if name else name

    c_spacer, c_prof = st.columns([4.2, 1.4])
    with c_prof:
        with st.popover(f"🟢 [{first_letter}]  {first_name}", use_container_width=True):
            st.markdown(
                f'''<div style="text-align:center;padding:0.4rem 0 0.6rem;">
                    <div style="width:48px;height:48px;border-radius:50%;background:linear-gradient(135deg,#2563EB,#1D4ED8);color:#FFFFFF;display:inline-flex;align-items:center;justify-content:center;font-size:1.35rem;font-weight:750;margin-bottom:0.4rem;box-shadow:0 3px 10px rgba(37,99,235,0.4);">
                        {first_letter}
                    </div>
                    <div style="font-weight:700;font-size:1.02rem;color:var(--text);">{C.esc(name)}</div>
                    <div style="font-size:0.82rem;color:var(--muted);margin-bottom:0.4rem;word-break:break-all;">{C.esc(email)}</div>
                    <span class="iq-badge {'info' if role == 'recruiter' else 'success'}"><i></i>{role.title()} Account</span>
                </div>''',
                unsafe_allow_html=True
            )
            st.divider()
            with st.expander("🔒 Change Password"):
                old_pw = st.text_input("Current Password", type="password", key="_prof_old_pw")
                new_pw = st.text_input("New Password", type="password", key="_prof_new_pw", help="At least 8 characters, letters and numbers")
                cnew_pw = st.text_input("Confirm New Password", type="password", key="_prof_cnew_pw")
                if st.button("Update Password", type="primary", use_container_width=True, key="_prof_update_pw_btn"):
                    if not old_pw or not new_pw:
                        st.error("Please fill out all password fields.")
                    elif new_pw != cnew_pw:
                        st.error("New passwords do not match.")
                    else:
                        ok, r = api.request("POST", "/auth/change-password", json={
                            "current_password": old_pw,
                            "new_password": new_pw,
                            "confirm_new_password": cnew_pw
                        })
                        if ok:
                            if isinstance(r, dict) and "token" in r:
                                st.session_state["auth_token"] = r["token"]
                                st.query_params["session"] = r["token"]
                            st.toast("Password updated successfully!", icon="🔒")
                            st.success("Password changed successfully!")
                        else:
                            st.error(str(r))
            st.divider()
            if st.button("🚪  Log Out", key="popover_logout_action", use_container_width=True):
                api.logout()
                st.rerun()


if user_role in ("recruiter", "candidate"):
    with st.sidebar:
        C.brand()

        if user_role == "recruiter":
            u_name = current_user.get("name", "Recruiter") if current_user else "Recruiter"
            u_email = current_user.get("email", "") if current_user else ""
            st.markdown(
                f'''<div style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);padding:0.75rem 0.9rem;margin-bottom:0.7rem;">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.25rem;">
                        <span style="font-weight:700;font-size:0.92rem;color:var(--text);">{C.esc(u_name)}</span>
                        <span class="iq-badge info" style="font-size:0.72rem;padding:0.15rem 0.5rem;">Recruiter</span>
                    </div>
                    <div style="font-size:0.8rem;color:var(--muted);overflow:hidden;text-overflow:ellipsis;">{C.esc(u_email)}</div>
                </div>''',
                unsafe_allow_html=True
            )
            if st.button("🚪  Log Out", key="recruiter_logout", use_container_width=True):
                api.logout()
                st.rerun()

            C.side_label("Recruiter Workspace")
            page = st.radio(
                "Navigation",
                list(RECRUITER_PAGES),
                label_visibility="collapsed",
                key="nav_recruiter",
                format_func=lambda k: RECRUITER_LABELS.get(k, k)
            )

        elif user_role == "candidate":
            u_name = current_user.get("name", "Candidate") if current_user else "Candidate"
            u_email = current_user.get("email", "") if current_user else ""
            st.markdown(
                f'''<div style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);padding:0.75rem 0.9rem;margin-bottom:0.7rem;">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.25rem;">
                        <span style="font-weight:700;font-size:0.92rem;color:var(--text);">{C.esc(u_name)}</span>
                        <span class="iq-badge success" style="font-size:0.72rem;padding:0.15rem 0.5rem;">Candidate</span>
                    </div>
                    <div style="font-size:0.8rem;color:var(--muted);overflow:hidden;text-overflow:ellipsis;">{C.esc(u_email)}</div>
                </div>''',
                unsafe_allow_html=True
            )

            # Multi-application selector if candidate has several applications
            if api.is_authenticated():
                cand_apps = api.call("GET", "/portal/applications", quiet=True) or []
                if len(cand_apps) > 1:
                    app_map = {a["access_token"]: f"{a['job_title']} (#{a['application_id']})" for a in cand_apps}
                    active_tok = st.session_state.get("cand_token")
                    curr_idx = list(app_map.keys()).index(active_tok) if active_tok in app_map else 0
                    sel_tok = st.selectbox(
                        "Active Application",
                        list(app_map.keys()),
                        index=curr_idx,
                        format_func=lambda t: app_map[t],
                        key="cand_active_app"
                    )
                    if sel_tok != active_tok:
                        st.session_state["cand_token"] = sel_tok
                        st.rerun()
                elif len(cand_apps) == 1 and not st.session_state.get("cand_token"):
                    st.session_state["cand_token"] = cand_apps[0]["access_token"]

            if st.button("🚪  Log Out", key="candidate_logout", use_container_width=True):
                api.logout()
                st.session_state.pop("cand_token", None)
                st.rerun()

            C.side_label("Candidate Workspace")
            page = st.radio("Navigation", candidate.PAGES, label_visibility="collapsed", key="nav_candidate")

        C.side_label("System Status")
        if cfg:
            llm_label = "Rule-based (Demo)" if cfg.get("demo_llm") else f"{cfg.get('llm_provider', 'LLM').title()} ({cfg.get('llm_model') or 'Default'})"
            idm_label = "Simulated Check" if cfg.get("identity_is_demo") else "Automated Check"
            st.markdown(
                f'<div class="iq-mode" style="display:flex;flex-direction:column;gap:0.4rem;">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                f'<span style="color:var(--muted);font-size:0.76rem;">AI Engine</span>'
                f'<span style="color:var(--text);font-weight:650;font-size:0.8rem;">{llm_label}</span>'
                f'</div>'
                f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                f'<span style="color:var(--muted);font-size:0.76rem;">Verification</span>'
                f'<span style="color:var(--text);font-weight:650;font-size:0.8rem;">{idm_label}</span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        else:
            C.callout("error", "Backend offline", "Run run_backend.bat")


# Main content router
if cfg is None:
    C.page_header("Cannot reach backend server", "InterviewIQ requires the backend API server.")
    C.callout("error", "Backend offline", f"Expected at {api.API}. Open a terminal and run run_backend.bat, then refresh this page.")
elif user_role == "recruiter":
    render_top_corner_profile(current_user, user_role)
    api.show_flash()
    RECRUITER_PAGES[page]()
elif user_role == "candidate":
    render_top_corner_profile(current_user, user_role)
    api.show_flash()
    candidate.render(page)
else:
    auth.render()
