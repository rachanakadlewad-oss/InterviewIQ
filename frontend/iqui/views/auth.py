"""Authentication view for InterviewIQ.
Modern, professional login & registration with persistent session handling,
strict role-based access control, and dropdown role selection."""
import re
import streamlit as st

from .. import api, components as C


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))


def render():
    """Renders the modern, professional authentication card."""
    st.markdown(
        """
        <div style="text-align: center; margin-top: 1.5rem; margin-bottom: 1.8rem;">
            <div style="display: inline-flex; align-items: center; justify-content: center; width: 52px; height: 52px; border-radius: 12px; background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%); color: #FFFFFF; font-weight: 800; font-size: 22px; box-shadow: 0 4px 16px rgba(37,99,235,0.45); margin-bottom: 0.85rem;">
                IQ
            </div>
            <h1 style="font-size: 2.1rem; font-weight: 800; margin: 0; color: var(--text); letter-spacing: -0.02em;">InterviewIQ</h1>
            <p style="color: var(--text2); font-size: 1.0rem; margin-top: 0.4rem; font-weight: 500;">
                AI-Powered Autonomous Talent Assessment Platform
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, center_col, _ = st.columns([1, 1.65, 1])

    with center_col:
        with st.container(border=True):
            # 1. Role Selection via proper Dropdown
            selected_role_label = st.selectbox(
                "Select Role",
                ["Recruiter", "Candidate"],
                index=0,
                key="_auth_role_dropdown",
                help="Choose whether you are accessing as a Recruiter or Candidate."
            )
            selected_role = selected_role_label.lower()
            role_title = selected_role_label

            # 2. Auth Mode Tab (Log In vs Create Account)
            mode = st.radio(
                "Action",
                ["Log In", "Create Account"],
                horizontal=True,
                label_visibility="collapsed",
                key=f"_auth_mode_{selected_role}"
            )
            is_signup = (mode == "Create Account")

            badge_tone = "info" if selected_role == "recruiter" else "success"
            st.markdown(
                f"""
                <div style="margin: 0.65rem 0 1.25rem 0; padding-bottom: 0.85rem; border-bottom: 1px solid var(--border);">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <h3 style="margin: 0; font-size: 1.25rem; font-weight: 700; color: var(--text);">
                            {role_title} {"Sign Up" if is_signup else "Sign In"}
                        </h3>
                        <span class="iq-badge {badge_tone}">
                            <i></i>{role_title} Workspace
                        </span>
                    </div>
                    <p style="margin: 0.35rem 0 0 0; color: var(--muted); font-size: 0.88rem;">
                        {"Create a new " + role_title.lower() + " account to manage your hiring pipeline." if is_signup and selected_role == "recruiter" else ("Create a candidate account to apply and track your interview." if is_signup else "Enter your credentials to access your " + role_title.lower() + " portal.")}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Form fields
            name = ""
            if is_signup:
                name = st.text_input(
                    "Full Name",
                    placeholder="e.g. Rachana Kadlewad" if selected_role == "recruiter" else "e.g. Alex Smith",
                    key=f"signup_name_{selected_role}"
                )

            email = st.text_input(
                "Email Address",
                placeholder="name@company.com" if selected_role == "recruiter" else "candidate@example.com",
                key=f"auth_email_{selected_role}"
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter password (min 8 characters)",
                key=f"auth_pw_{selected_role}"
            )

            confirm_password = ""
            if is_signup:
                confirm_password = st.text_input(
                    "Confirm Password",
                    type="password",
                    placeholder="Re-enter password",
                    key=f"signup_cpw_{selected_role}"
                )

            st.markdown("<div style='height: 0.4rem;'></div>", unsafe_allow_html=True)
            btn_label = f"Create {role_title} Account" if is_signup else f"Sign In as {role_title}"
            submit = st.button(btn_label, type="primary", use_container_width=True, key=f"auth_submit_{selected_role}")

            if submit:
                # Validation checks
                err = None
                if is_signup and not name.strip():
                    err = "Please enter your full name."
                elif not email.strip():
                    err = "Please enter your email address."
                elif not _is_valid_email(email):
                    err = "Please enter a valid email address (e.g. user@domain.com)."
                elif not password:
                    err = "Please enter your password."
                elif is_signup and len(password) < 8:
                    err = "Password must be at least 8 characters long."
                elif is_signup and password != confirm_password:
                    err = "Password confirmation does not match. Please re-enter."

                if err:
                    C.callout("error", "Validation Error", err)
                else:
                    with st.spinner("Verifying credentials..."):
                        if is_signup:
                            ok, res = api.signup(
                                name=name,
                                email=email,
                                password=password,
                                confirm_password=confirm_password,
                                role=selected_role
                            )
                        else:
                            ok, res = api.login(
                                email=email,
                                password=password,
                                role=selected_role
                            )

                    if not ok:
                        C.callout("error", "Authentication Failed", str(res))
                    else:
                        st.session_state["role"] = role_title
                        if selected_role == "candidate":
                            apps = api.call("GET", "/portal/applications", quiet=True)
                            if apps and len(apps) > 0:
                                st.session_state["cand_token"] = apps[0]["access_token"]
                        st.rerun()

            st.markdown("<div style='height: 0.35rem;'></div>", unsafe_allow_html=True)
            if not is_signup:
                st.markdown(
                    "<div style='text-align:center;font-size:0.86rem;color:var(--muted);margin-top:0.6rem;'>"
                    "Don't have an account yet? Select <b>Create Account</b> above to register."
                    "</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    "<div style='text-align:center;font-size:0.86rem;color:var(--muted);margin-top:0.6rem;'>"
                    "Already have an account? Select <b>Log In</b> above."
                    "</div>",
                    unsafe_allow_html=True
                )

        # Direct token login option for candidates who received an email invite
        if selected_role == "candidate":
            st.markdown("<div style='height: 0.6rem;'></div>", unsafe_allow_html=True)
            with st.expander("🔑 Have an interview invite link or access token?"):
                st.caption(
                    "If you received an interview invitation with an access token, you can directly access your application without logging in."
                )
                direct_token = st.text_input(
                    "Interview Access Token",
                    type="password",
                    placeholder="Paste access token from invite email",
                    key="_auth_direct_cand_token"
                )
                if st.button("Access Interview", type="secondary", use_container_width=True):
                    if not direct_token.strip():
                        C.callout("error", "Missing Token", "Please enter your access token.")
                    else:
                        ok, data = api.request("GET", "/portal/me", token=direct_token.strip())
                        if ok:
                            st.session_state["cand_token"] = direct_token.strip()
                            st.session_state["role"] = "Candidate"
                            st.rerun()
                        else:
                            C.callout("error", "Invalid Token", "We could not verify this interview token. Please check and try again.")
