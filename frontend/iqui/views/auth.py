"""Authentication view for InterviewIQ.
Supports separate login and registration for Recruiters and Candidates,
plus direct interview token access for candidate invites."""
import re
import streamlit as st

from .. import api, components as C


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))


def render():
    """Renders the centralized modern authentication experience."""
    st.markdown(
        """
        <div style="text-align: center; margin-top: 1.5rem; margin-bottom: 2rem;">
            <div style="display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 12px; background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%); color: #fff; font-weight: 800; font-size: 20px; box-shadow: 0 4px 14px rgba(37,99,235,0.4); margin-bottom: 0.75rem;">
                IQ
            </div>
            <h1 style="font-size: 1.85rem; font-weight: 700; margin: 0; color: var(--text);">InterviewIQ</h1>
            <p style="color: var(--text2); font-size: 0.92rem; margin-top: 0.35rem;">
                AI-Powered Autonomous Talent Assessment Platform
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, center_col, _ = st.columns([1, 1.8, 1])

    with center_col:
        # Step 1: Role Selection Tabs
        role_tab = st.radio(
            "Select Your Portal",
            ["💼 Recruiter", "👤 Candidate"],
            horizontal=True,
            label_visibility="collapsed",
            key="_auth_role_tab"
        )
        selected_role = "recruiter" if "Recruiter" in role_tab else "candidate"

        # Step 2: Auth Mode (Log In vs Create Account)
        with st.container(border=True):
            mode = st.radio(
                "Action",
                ["Log In", "Create Account"],
                horizontal=True,
                label_visibility="collapsed",
                key=f"_auth_mode_{selected_role}"
            )

            is_signup = (mode == "Create Account")
            role_title = "Recruiter" if selected_role == "recruiter" else "Candidate"

            st.markdown(
                f"""
                <div style="margin: 0.75rem 0 1.25rem 0; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border);">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <h3 style="margin: 0; font-size: 1.2rem; font-weight: 650; color: var(--text);">
                            {role_title} {"Sign Up" if is_signup else "Sign In"}
                        </h3>
                        <span class="iq-badge {'info' if selected_role == 'recruiter' else 'success'}">
                            <i></i>{role_title} Role
                        </span>
                    </div>
                    <p style="margin: 0.3rem 0 0 0; color: var(--muted); font-size: 0.82rem;">
                        {"Create a new " + role_title.lower() + " account to get started." if is_signup else "Sign in to access your " + role_title.lower() + " workspace."}
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
                    placeholder="e.g. Jane Doe",
                    key=f"signup_name_{selected_role}"
                )

            email = st.text_input(
                "Email Address",
                placeholder="e.g. name@company.com" if selected_role == "recruiter" else "e.g. candidate@example.com",
                key=f"auth_email_{selected_role}"
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="At least 8 characters",
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

            btn_label = f"Create {role_title} Account" if is_signup else f"Sign In as {role_title}"
            submit = st.button(btn_label, type="primary", use_container_width=True, key=f"auth_submit_{selected_role}")

            if submit:
                # Validation
                err = None
                if is_signup and not name.strip():
                    err = "Please enter your full name."
                elif not email.strip():
                    err = "Please enter your email address."
                elif not _is_valid_email(email):
                    err = "Please enter a valid email address."
                elif not password:
                    err = "Please enter your password."
                elif is_signup and len(password) < 8:
                    err = "Password must be at least 8 characters long."
                elif is_signup and password != confirm_password:
                    err = "Password confirmation does not match."

                if err:
                    C.callout("error", "Validation error", err)
                else:
                    with st.spinner("Authenticating..."):
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
                        # For candidate accounts, auto-discover any linked applications
                        if selected_role == "candidate":
                            apps = api.call("GET", "/portal/applications", quiet=True)
                            if apps and len(apps) > 0:
                                st.session_state["cand_token"] = apps[0]["access_token"]
                        st.rerun()

            st.markdown("<div style='height: 0.25rem;'></div>", unsafe_allow_html=True)
            if not is_signup:
                st.markdown(
                    "<div style='text-align:center;font-size:0.82rem;color:var(--muted);margin-top:0.5rem;'>"
                    "Don't have an account yet? Switch to <b>Create Account</b> above to register."
                    "</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    "<div style='text-align:center;font-size:0.82rem;color:var(--muted);margin-top:0.5rem;'>"
                    "Already have an account? Switch to <b>Log In</b> above."
                    "</div>",
                    unsafe_allow_html=True
                )

        # Direct token login option for candidates who received an email invite
        if selected_role == "candidate":
            st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
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
                        C.callout("error", "Missing token", "Please enter your access token.")
                    else:
                        ok, data = api.request("GET", "/portal/me", token=direct_token.strip())
                        if ok:
                            st.session_state["cand_token"] = direct_token.strip()
                            st.session_state["role"] = "Candidate"
                            st.rerun()
                        else:
                            C.callout("error", "Invalid Token", "We could not verify this interview token. Please check and try again.")
