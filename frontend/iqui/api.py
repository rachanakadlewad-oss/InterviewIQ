"""Thin HTTP client for the FastAPI backend + Streamlit navigation & auth helpers."""
import os
from typing import Any, Optional, Tuple

import requests
import streamlit as st

from . import components as C

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
KEY = os.getenv("RECRUITER_API_KEY", "")


def _detail(r) -> str:
    try:
        d = r.json().get("detail", r.text)
    except Exception:
        return r.text[:300]
    if isinstance(d, list):  # FastAPI validation errors
        return "; ".join(f"{'.'.join(str(x) for x in e.get('loc', [])[1:])}: {e.get('msg')}" for e in d)
    return str(d)


def request(method: str, path: str, token: Optional[str] = None, **kw) -> Tuple[bool, Any]:
    """Returns (ok, data_or_error_message). Never raises, never renders."""
    headers = kw.pop("headers", None) or {}
    if KEY and "X-API-Key" not in headers:
        headers["X-API-Key"] = KEY
    if token:
        headers["X-Access-Token"] = token

    # Forward active user auth JWT token if logged in or restored from query params
    auth_token = st.session_state.get("auth_token") or st.query_params.get("session")
    if auth_token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {auth_token}"
        headers["X-Auth-Token"] = auth_token

    try:
        r = requests.request(method, API + path, headers=headers, timeout=120, **kw)
    except requests.RequestException:
        return False, f"Cannot reach the backend at {API}. Start it with run_backend.bat."

    if r.status_code >= 400:
        msg = _detail(r)
        if r.status_code == 409:
            msg = f"Blocked: {msg}"
        elif r.status_code == 401:
            msg = f"Not authorised: {msg}"
        elif r.status_code == 403:
            msg = f"Access denied: {msg}"
        return False, msg
    return True, r.json()


def call(method: str, path: str, token: Optional[str] = None, quiet: bool = False, **kw):
    ok, data = request(method, path, token, **kw)
    if not ok:
        if not quiet:
            C.callout("error", "Error", data)
        return None
    return data


# ---- auth helpers & persistence across page refresh ------------------------
def restore_session():
    """Restores user session across page refreshes using URL query params and backend token validation."""
    if not st.session_state.get("auth_token"):
        q_sess = st.query_params.get("session")
        if q_sess and isinstance(q_sess, str) and len(q_sess) > 20:
            ok, user_data = request("GET", "/auth/me", headers={"Authorization": f"Bearer {q_sess}"})
            if ok and isinstance(user_data, dict) and "id" in user_data:
                st.session_state["auth_token"] = q_sess
                st.session_state["auth_user"] = user_data
                st.session_state["role"] = user_data["role"].capitalize()
            else:
                try:
                    del st.query_params["session"]
                except Exception:
                    pass


def signup(name: str, email: str, password: str, confirm_password: str, role: str) -> Tuple[bool, Any]:
    ok, data = request("POST", "/auth/signup", json={
        "name": name.strip(),
        "email": email.strip().lower(),
        "password": password,
        "confirm_password": confirm_password,
        "role": role.lower()
    })
    if ok and isinstance(data, dict) and "token" in data:
        st.session_state["auth_token"] = data["token"]
        st.session_state["auth_user"] = data["user"]
        st.session_state["role"] = data["user"]["role"].capitalize()
        st.query_params["session"] = data["token"]
        return True, data["user"]
    return False, data


def login(email: str, password: str, role: str) -> Tuple[bool, Any]:
    ok, data = request("POST", "/auth/login", json={
        "email": email.strip().lower(),
        "password": password,
        "role": role.lower()
    })
    if ok and isinstance(data, dict) and "token" in data:
        st.session_state["auth_token"] = data["token"]
        st.session_state["auth_user"] = data["user"]
        st.session_state["role"] = data["user"]["role"].capitalize()
        st.query_params["session"] = data["token"]
        return True, data["user"]
    return False, data


def logout() -> bool:
    try:
        request("POST", "/auth/logout")
    except Exception:
        pass
    try:
        del st.query_params["session"]
    except Exception:
        pass
    st.session_state.clear()
    return True


def is_authenticated() -> bool:
    return bool(st.session_state.get("auth_token"))


def get_current_user() -> Optional[dict]:
    return st.session_state.get("auth_user")


def get_current_role() -> Optional[str]:
    user = get_current_user()
    if user:
        return user.get("role")
    return None


def config():
    return call("GET", "/config", quiet=True)


# ---- candidate & recruiter endpoints ----------------------------------------
def get_recruiter_candidates(job_id: Optional[int] = None, status: Optional[str] = None, search: Optional[str] = None):
    params = []
    if job_id:
        params.append(f"job_id={job_id}")
    if status and status != "All":
        params.append(f"status={status}")
    if search:
        params.append(f"search={requests.utils.quote(search)}")
    qs = ("?" + "&".join(params)) if params else ""
    return call("GET", f"/recruiter/candidates{qs}") or []


def get_candidate_counts(job_id: Optional[int] = None) -> dict:
    qs = f"?job_id={job_id}" if job_id else ""
    return call("GET", f"/recruiter/candidates/counts{qs}", quiet=True) or {
        "total": 0, "active": 0, "shortlisted": 0, "pending": 0, "accepted": 0, "rejected": 0
    }


def update_candidate_status(application_id: int, action: str, notes: Optional[str] = None) -> bool:
    ok, res = request("PATCH", f"/applications/{application_id}/status", json={"action": action, "notes": notes or ""})
    if ok:
        act_label = {
            "SHORTLIST": "Shortlisted",
            "REJECT": "Rejected",
            "PENDING": "Moved to Review Queue",
            "PENDING_REVIEW": "Moved to Review Queue",
            "ACCEPT": "Accepted"
        }.get(action.upper(), action.title())
        flash("success", "Candidate Status Updated", f"Candidate #{application_id} marked as {act_label}.")
        return True
    flash("error", "Status Update Failed", str(res))
    return False


def rescore_candidate(application_id: int):
    return call("POST", f"/applications/{application_id}/rescore")


# ---- navigation -------------------------------------------------------------
PAGE_MAP = {
    "Overview": "Dashboard",
    "Shortlist & Scheduling": "Candidates",
    "Identity Review": "Interviews",
    "Reports & Decisions": "Reports",
}


def go(page: str, role: str = "recruiter"):
    """on_click callback: switch the sidebar navigation."""
    if role == "recruiter":
        page = PAGE_MAP.get(page, page)
    st.session_state[f"nav_{role}"] = page


def flash(tone: str, title: str, body: str = ""):
    """Queue a message that survives st.rerun() and is shown at the top of the next render."""
    st.session_state.setdefault("_flash", []).append((tone, title, body))


def show_flash():
    for tone, title, body in st.session_state.pop("_flash", []):
        C.callout(tone, title, body)


def select_job_next_run(job_id: int):
    """A widget key cannot be changed after the widget exists in the same run, so hand the choice to the next run."""
    st.session_state["_new_job_id"] = job_id


def job_picker(label: str = "Job") -> Optional[int]:
    """Shared job selector; the choice persists across recruiter pages."""
    if "_new_job_id" in st.session_state:
        st.session_state["job_id"] = st.session_state.pop("_new_job_id")
    jobs = call("GET", "/jobs") or []
    if not jobs:
        C.empty_state("No jobs yet", "Create your first job opening to start receiving candidates.")
        st.button("Create a Job", on_click=go, args=("Jobs",), type="primary")
        return None
    ids = [j["id"] for j in jobs]
    if st.session_state.get("job_id") not in ids:
        st.session_state["job_id"] = ids[0]
    st.selectbox(label, ids, key="job_id", format_func=lambda i: next(f"{j['title']}  (#{j['id']})" for j in jobs if j["id"] == i))
    return st.session_state["job_id"]
