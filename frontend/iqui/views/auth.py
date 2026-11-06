"""Authentication view for InterviewIQ.
Premium AI SaaS Redesign:
- Abstract blue futuristic technology background with high-contrast dark overlay.
- Balanced two-section interface (Left: Branding & AI Capabilities, Right: Glassmorphic Auth Card).
- Dropdown role selection (Recruiter / Candidate) with icons.
- Modern segmented tab toggle (Log In vs Create Account).
- Input field styling with icons and clear validation states.
- Enhanced primary buttons with hover/elevation effects.
- Direct interview token access for candidates with invite tokens.
"""
import base64
import html
import re
from pathlib import Path
import streamlit as st

from .. import api, components as C


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))


def _get_bg_data_uri() -> str:
    """Loads and base64-encodes the futuristic blue abstract background image."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    possible_paths = [
        base_dir / "assets" / "interviewiq_login_bg.jpg",
        base_dir / "assets" / "interviewiq_login_bg.png",
        base_dir.parent / "runtime" / "interviewiq_login_bg.jpg",
    ]
    for bg_path in possible_paths:
        if bg_path.exists():
            encoded = base64.b64encode(bg_path.read_bytes()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
    return ""


def render():
    """Renders the premium, futuristic AI recruitment platform login & registration view."""
    bg_uri = _get_bg_data_uri()

    # Dynamic CSS styling with full-viewport background, glassmorphism, and responsive two-column grid
    css_content = f"""
    <style>
    /* Hide sidebar on unauthenticated authentication landing */
    [data-testid="stSidebar"] {{
        display: none !important;
    }}

    /* Full page abstract futuristic background with high-contrast gradient overlay */
    [data-testid="stAppViewContainer"] {{
        background: 
            radial-gradient(circle at 14% 28%, rgba(37, 99, 235, 0.24) 0%, transparent 48%),
            radial-gradient(circle at 86% 72%, rgba(16, 185, 129, 0.12) 0%, transparent 42%),
            linear-gradient(135deg, rgba(11, 15, 25, 0.88) 0%, rgba(13, 20, 36, 0.91) 50%, rgba(11, 15, 25, 0.96) 100%),
            url('{bg_uri}') !important;
        background-size: cover !important;
        background-position: center !important;
        background-repeat: no-repeat !important;
        background-attachment: fixed !important;
    }}

    /* Container width & vertical breathing room */
    .block-container {{
        max-width: 1240px !important;
        padding-top: 2.2rem !important;
        padding-bottom: 3.5rem !important;
        margin: 0 auto !important;
    }}

    /* Glassmorphic Auth Container */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: rgba(17, 27, 48, 0.84) !important;
        backdrop-filter: blur(20px) !important;
        -webkit-backdrop-filter: blur(20px) !important;
        border: 1px solid rgba(59, 130, 246, 0.35) !important;
        border-radius: 18px !important;
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.65), 0 0 35px rgba(37, 99, 235, 0.16) !important;
        padding: 1.6rem 1.85rem 2.0rem !important;
        transition: border-color 0.25s ease, box-shadow 0.25s ease !important;
    }}

    div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
        border-color: rgba(59, 130, 246, 0.52) !important;
        box-shadow: 0 28px 70px rgba(0, 0, 0, 0.72), 0 0 45px rgba(37, 99, 235, 0.24) !important;
    }}

    /* Feature highlight pill in left branding section */
    .iq-brand-feature {{
        display: flex;
        align-items: flex-start;
        gap: 0.95rem;
        background: rgba(15, 23, 42, 0.68);
        border: 1px solid rgba(35, 53, 84, 0.85);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 0.95rem 1.15rem;
        margin-bottom: 0.85rem;
        transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
    }}

    .iq-brand-feature:hover {{
        transform: translateX(4px);
        border-color: rgba(59, 130, 246, 0.5);
        background: rgba(22, 34, 56, 0.85);
    }}

    .iq-brand-icon-box {{
        width: 42px;
        height: 42px;
        border-radius: 10px;
        background: linear-gradient(135deg, rgba(37, 99, 235, 0.25), rgba(30, 64, 175, 0.45));
        border: 1px solid rgba(59, 130, 246, 0.4);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        flex-shrink: 0;
        color: #60A5FA;
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
    }}

    .iq-brand-feature-title {{
        font-weight: 700;
        font-size: 0.96rem;
        color: #FFFFFF;
        margin-bottom: 0.2rem;
        letter-spacing: -0.01em;
    }}

    .iq-brand-feature-desc {{
        font-size: 0.85rem;
        color: #94A3B8;
        line-height: 1.48;
    }}

    /* AI Status Badge */
    .iq-ai-pill-tag {{
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        background: rgba(37, 99, 235, 0.18);
        border: 1px solid rgba(59, 130, 246, 0.45);
        border-radius: 999px;
        padding: 0.35rem 0.9rem;
        font-size: 0.76rem;
        font-weight: 700;
        color: #93C5FD;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        margin-bottom: 0.95rem;
        box-shadow: 0 2px 10px rgba(37, 99, 235, 0.2);
    }}

    .iq-ai-pill-tag i {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #3B82F6;
        display: inline-block;
        box-shadow: 0 0 10px #3B82F6;
        animation: iqPulseDot 2s infinite ease-in-out;
    }}

    @keyframes iqPulseDot {{
        0%, 100% {{ transform: scale(1); opacity: 0.7; }}
        50% {{ transform: scale(1.3); opacity: 1; }}
    }}

    /* Segmented Mode Selector (Log In / Create Account) */
    div[data-testid="stRadio"] [role="radiogroup"] {{
        background: #090E1B !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        padding: 4px !important;
        gap: 6px !important;
        margin-top: 0.35rem !important;
        margin-bottom: 0.75rem !important;
    }}

    div[data-testid="stRadio"] [role="radiogroup"] label {{
        flex: 1 !important;
        text-align: center !important;
        border-radius: 7px !important;
        padding: 0.55rem 0.85rem !important;
        margin: 0 !important;
        justify-content: center !important;
        font-weight: 650 !important;
        font-size: 0.92rem !important;
        color: var(--text2) !important;
        border: 1px solid transparent !important;
        transition: all 0.18s ease !important;
        cursor: pointer !important;
    }}

    div[data-testid="stRadio"] [role="radiogroup"] label:hover {{
        color: #FFFFFF !important;
        background: rgba(37, 99, 235, 0.12) !important;
    }}

    div[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {{
        background: linear-gradient(135deg, var(--primary) 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        box-shadow: 0 2px 10px rgba(37, 99, 235, 0.45) !important;
        border-color: rgba(59, 130, 246, 0.6) !important;
    }}

    div[data-testid="stRadio"] [role="radiogroup"] label p {{
        text-align: center !important;
        width: 100% !important;
        margin: 0 !important;
    }}

    /* Input field enhancement */
    [data-baseweb="input"] {{
        background: rgba(11, 17, 31, 0.85) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
        transition: all 0.2s ease !important;
    }}

    [data-baseweb="input"]:focus-within {{
        border-color: var(--primary-hover) !important;
        box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.35) !important;
        background: rgba(11, 17, 31, 0.98) !important;
    }}

    /* Primary action button */
    .stButton>button[kind="primary"] {{
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
        border: 1px solid #3B82F6 !important;
        border-radius: 9px !important;
        font-size: 0.98rem !important;
        font-weight: 700 !important;
        padding: 0.65rem 1.4rem !important;
        letter-spacing: -0.01em !important;
        box-shadow: 0 4px 16px rgba(37, 99, 235, 0.4) !important;
        transition: all 0.2s ease !important;
    }}

    .stButton>button[kind="primary"]:hover {{
        background: linear-gradient(135deg, #3B82F6 0%, #2563EB 100%) !important;
        border-color: #60A5FA !important;
        box-shadow: 0 6px 22px rgba(37, 99, 235, 0.55) !important;
        transform: translateY(-1px) !important;
    }}

    .stButton>button[kind="primary"]:active {{
        transform: translateY(1px) !important;
    }}
    </style>
    """
    C._emit(css_content)

    # Balanced Two-Section Responsive Layout
    col_brand, col_auth = st.columns([1.18, 1.0], gap="large")

    # =========================================================================
    # LEFT SECTION: BRANDING, VALUE PROPOSITION & AI RECRUITMENT CAPABILITIES
    # =========================================================================
    with col_brand:
        brand_html = """
        <div style="padding-right: 1.0rem;">
            <div class="iq-ai-pill-tag">
                <i></i> Autonomous AI Recruitment Platform
            </div>

            <div style="display: flex; align-items: center; gap: 0.95rem; margin-bottom: 0.85rem;">
                <div style="width: 52px; height: 52px; border-radius: 14px; background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%); color: #FFFFFF; display: inline-flex; align-items: center; justify-content: center; font-weight: 850; font-size: 1.45rem; box-shadow: 0 4px 20px rgba(37,99,235,0.55); border: 1px solid rgba(255,255,255,0.2);">
                    IQ
                </div>
                <div>
                    <div style="font-size: 2.5rem; font-weight: 850; letter-spacing: -0.03em; color: #FFFFFF; line-height: 1.05;">
                        Interview<span style="color: #3B82F6;">IQ</span>
                    </div>
                    <div style="font-size: 0.82rem; font-weight: 600; color: #94A3B8; letter-spacing: 0.05em; text-transform: uppercase;">
                        Next-Gen Autonomous Talent Assessment
                    </div>
                </div>
            </div>

            <div style="font-size: 1.48rem; font-weight: 750; color: #E2E8F0; margin: 1.1rem 0 0.5rem; letter-spacing: -0.02em;">
                Smarter Hiring. <span style="color: #60A5FA;">Better Talent.</span>
            </div>
            <p style="color: #94A3B8; font-size: 0.96rem; line-height: 1.62; margin-bottom: 1.6rem; max-width: 540px;">
                An AI-powered recruitment platform that simplifies candidate evaluation and makes hiring more intelligent. Conduct autonomous adaptive interviews, screen candidates with evidence-backed LLM matching, and identify top performers effortlessly.
            </p>

            <div class="iq-brand-feature">
                <div class="iq-brand-icon-box">🎙️</div>
                <div>
                    <div class="iq-brand-feature-title">Autonomous Multi-Turn AI Interviews</div>
                    <div class="iq-brand-feature-desc">Adaptive conversational voice and text interviews that dynamically probe technical competencies, project depth, and problem-solving skills.</div>
                </div>
            </div>

            <div class="iq-brand-feature">
                <div class="iq-brand-icon-box">🧠</div>
                <div>
                    <div class="iq-brand-feature-title">Evidence-Based LLM Candidate Matching</div>
                    <div class="iq-brand-feature-desc">Deep semantic resume-job evaluation that assesses real-world project impact and proven capabilities—far beyond naive keyword matching.</div>
                </div>
            </div>

            <div class="iq-brand-feature">
                <div class="iq-brand-icon-box">🛡️</div>
                <div>
                    <div class="iq-brand-feature-title">Anti-Proxy & Identity Verification</div>
                    <div class="iq-brand-feature-desc">Automated biometric checks and integrity monitoring that eliminate interview impersonation and guarantee trustworthy talent assessments.</div>
                </div>
            </div>

            <div style="display: flex; align-items: center; gap: 1.35rem; margin-top: 1.6rem; padding-top: 1.15rem; border-top: 1px solid rgba(35, 53, 84, 0.7); flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 0.4rem; color: #94A3B8; font-size: 0.82rem; font-weight: 600;">
                    <span style="color: #10B981;">🔒</span> Enterprise Data Security
                </div>
                <div style="display: flex; align-items: center; gap: 0.4rem; color: #94A3B8; font-size: 0.82rem; font-weight: 600;">
                    <span style="color: #3B82F6;">⚡</span> Sub-second AI Evaluation
                </div>
                <div style="display: flex; align-items: center; gap: 0.4rem; color: #94A3B8; font-size: 0.82rem; font-weight: 600;">
                    <span style="color: #F59E0B;">🎯</span> 100% Bias-Free Scoring
                </div>
            </div>
        </div>
        """
        C._emit(brand_html)

    # =========================================================================
    # RIGHT SECTION: AUTHENTICATION CARD (LOGIN & REGISTRATION)
    # =========================================================================
    with col_auth:
        with st.container(border=True):
            # 1. Role Selection via Dropdown with Role Icons
            role_options = ["Recruiter", "Candidate"]
            role_display_map = {
                "Recruiter": "👔 Recruiter  (Post Jobs, Screen & Review Candidates)",
                "Candidate": "🎓 Candidate  (Explore Jobs & Attend AI Interview)"
            }

            selected_role_label = st.selectbox(
                "Select Access Role",
                role_options,
                index=0,
                format_func=lambda r: role_display_map.get(r, r),
                key="_auth_role_dropdown",
                help="Choose your access portal. Recruiters manage requisitions; candidates attend adaptive interviews."
            )
            selected_role = selected_role_label.lower()
            role_title = selected_role_label

            # 2. Segmented Toggle: Log In vs Create Account
            mode = st.radio(
                "Authentication Action",
                ["Log In", "Create Account"],
                horizontal=True,
                label_visibility="collapsed",
                key=f"_auth_mode_{selected_role}"
            )
            is_signup = (mode == "Create Account")

            # Header info inside the card
            badge_tone = "info" if selected_role == "recruiter" else "success"
            role_icon = "👔" if selected_role == "recruiter" else "🎓"

            card_header_html = f"""
            <div style="margin: 0.35rem 0 1.15rem 0; padding-bottom: 0.85rem; border-bottom: 1px solid rgba(35, 53, 84, 0.8);">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <h3 style="margin: 0; font-size: 1.25rem; font-weight: 750; color: #FFFFFF; letter-spacing: -0.015em;">
                        {role_icon} {role_title} {"Registration" if is_signup else "Sign In"}
                    </h3>
                    <span class="iq-badge {badge_tone}" style="font-size: 0.74rem;">
                        <i></i>{role_title} Portal
                    </span>
                </div>
                <p style="margin: 0.35rem 0 0 0; color: #94A3B8; font-size: 0.88rem; line-height: 1.45;">
                    {"Create your recruiter account to configure job criteria and assess talent with AI." if is_signup and selected_role == "recruiter" else ("Create a candidate account to apply for positions and take autonomous interviews." if is_signup else "Enter your credentials to securely access your " + role_title.lower() + " dashboard.")}
                </p>
            </div>
            """
            C._emit(card_header_html)

            # 3. Form Input Fields with Visual Icons
            name = ""
            if is_signup:
                name = st.text_input(
                    "👤 Full Name",
                    placeholder="e.g. Rachana Kadlewad" if selected_role == "recruiter" else "e.g. Alex Smith",
                    key=f"signup_name_{selected_role}"
                )

            email = st.text_input(
                "✉️ Email Address",
                placeholder="name@company.com" if selected_role == "recruiter" else "candidate@example.com",
                key=f"auth_email_{selected_role}"
            )

            password = st.text_input(
                "🔒 Password",
                type="password",
                placeholder="Enter password (minimum 8 characters)",
                key=f"auth_pw_{selected_role}"
            )

            confirm_password = ""
            if is_signup:
                confirm_password = st.text_input(
                    "🛡️ Confirm Password",
                    type="password",
                    placeholder="Re-enter your password",
                    key=f"signup_cpw_{selected_role}"
                )

            st.markdown("<div style='height: 0.35rem;'></div>", unsafe_allow_html=True)

            # 4. Action Button with Dynamic Label & Accent Styling
            btn_label = f"✨ Create {role_title} Account" if is_signup else f"🚀 Sign In as {role_title}"
            submit = st.button(btn_label, type="primary", use_container_width=True, key=f"auth_submit_{selected_role}")

            if submit:
                # Validation rules
                err = None
                if is_signup and not name.strip():
                    err = "Please enter your full name."
                elif not email.strip():
                    err = "Please enter your email address."
                elif not _is_valid_email(email):
                    err = "Please enter a valid email address (e.g. user@company.com)."
                elif not password:
                    err = "Please enter your password."
                elif is_signup and len(password) < 8:
                    err = "Password must be at least 8 characters long for security."
                elif is_signup and password != confirm_password:
                    err = "Passwords do not match. Please ensure both passwords are identical."

                if err:
                    C.callout("error", "Validation Error", err)
                else:
                    with st.spinner(f"Authenticating {role_title.lower()} credentials with InterviewIQ..."):
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

            st.markdown("<div style='height: 0.25rem;'></div>", unsafe_allow_html=True)
            if not is_signup:
                st.markdown(
                    "<div style='text-align: center; font-size: 0.85rem; color: #94A3B8; margin-top: 0.5rem;'>"
                    "Don't have an account yet? Switch to <b>Create Account</b> above to register."
                    "</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    "<div style='text-align: center; font-size: 0.85rem; color: #94A3B8; margin-top: 0.5rem;'>"
                    "Already have an account? Switch to <b>Log In</b> above to sign in."
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
                    if st.button("🚀 Access Interview Directly", type="secondary", use_container_width=True):
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
