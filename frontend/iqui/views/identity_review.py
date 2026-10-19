import streamlit as st

from .. import api, components as C, helpers as H

RESOLUTIONS = {
    "approve_retry": ("Allow another attempt", "The candidate may repeat the identity check. The interview still cannot start until a check passes."),
    "approve_manual_pass": ("Verify manually and approve", "You vouch for the candidate's identity (e.g. by video call). Notes are required and the override is logged."),
    "reject": ("Close the application", "Ends the application and deletes the stored reference photo. Notes are required."),
}


def render():
    C.page_header("Identity Review", "Candidates whose identity check failed or was inconclusive wait here. "
                  "The interview cannot start - or continue - until a check passes or you approve it.", "Recruiter workspace")
    cfg = api.config() or {}
    if cfg.get("identity_is_demo"):
        C.callout("warning", "Identity verification is running on the DEMO ADAPTER",
                  "Outcomes are chosen from a selector, not from biometric analysis. The pass/fail gate and this review queue are real; the face matching is not.")
    elif cfg:
        C.callout("info", "Identity verification: basic OpenCV heuristic",
                  f"Face detection plus a weak similarity score (threshold {cfg.get('identity_threshold')}). Not biometric grade - human review is expected.")
    open_items = api.call("GET", "/reviews", params={"status": "OPEN"}) or []
    done_items = api.call("GET", "/reviews", params={"status": "RESOLVED"}) or []
    t_open, t_done = st.tabs([f"Open ({len(open_items)})", f"Resolved ({len(done_items)})"])
    with t_open:
        if not open_items:
            C.empty_state("No identity reviews waiting", "Failed or inconclusive checks will appear here automatically.")
        for it in open_items:
            review_card(it)
    with t_done:
        if not done_items:
            C.empty_state("Nothing resolved yet")
        else:
            C.table([("c", "Candidate", "strong"), ("job", "Job"), ("res", "Resolution"), ("notes", "Notes"), ("at", "Resolved")],
                    [{"c": r["candidate"], "job": r["job_title"], "res": RESOLUTIONS.get(r["resolution"], (r["resolution"],))[0],
                      "notes": r["notes"] or "-", "at": H.fmt_dt(r["resolved_at"])} for r in done_items])


def identity_table(log):
    C.table([("t", "Time", "strong"), ("type", "Check"), ("backend", "Method"), ("faces", "Faces", "r"), ("conf", "Confidence / threshold"),
             ("res", "Result"), ("why", "Reason")],
            [{"t": H.fmt_dt(e["timestamp"]), "type": e["check_type"].replace("_", " "), "backend": e["backend"],
              "faces": e["face_count"], "conf": f"{e['match_confidence']:.2f} / {e['threshold']:.2f}",
              "res": C.badge("Passed", "success") if e["passed"] else C.badge("Inconclusive" if e.get("inconclusive") else "Failed", "error"),
              "why": e["reason"]} for e in log])


def review_card(it):
    with st.container(border=True):
        C.badges(C.badge("Needs review", "warning"), C.badge(it["job_title"] or "Job", "neutral", dot=False))
        st.markdown(f"### {it['candidate'] or 'Application #' + str(it['application_id'])}")
        C.kv([("Raised", H.fmt_dt(it["created_at"])), ("Application", f"#{it['application_id']}"), ("Reason", it["reason"])])
        rep = api.call("GET", f"/applications/{it['application_id']}/report", quiet=True)
        if rep and rep["identity_log"]:
            st.markdown("**Identity check history**")
            identity_table(rep["identity_log"])
            if any(not e.get("is_real_biometric", False) for e in rep["identity_log"]):
                st.caption("Entries from the demo adapter or the OpenCV heuristic are not real biometric verification.")
        key = it["id"]
        res = st.radio("Resolution", list(RESOLUTIONS), key=f"res{key}", format_func=lambda k: RESOLUTIONS[k][0], horizontal=False)
        st.caption(RESOLUTIONS[res][1])
        notes = st.text_input("Notes" + (" (required)" if res != "approve_retry" else " (optional)"), key=f"notes{key}")
        if st.button("Apply resolution", key=f"apply{key}", type="primary"):
            if res != "approve_retry" and not notes.strip():
                C.callout("error", "Notes are required", "Explain why you are approving or closing this case; it is stored in the audit log.")
            elif api.call("POST", f"/reviews/{key}/resolve", json={"resolution": res, "notes": notes}):
                api.flash("success", "Review resolved", RESOLUTIONS[res][0])
                st.rerun()
