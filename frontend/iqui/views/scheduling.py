from datetime import date, datetime

import streamlit as st

from .. import api, components as C, helpers as H


def render():
    C.page_header("Shortlist & Scheduling", "Confirm who moves forward, then book each candidate into a free interview slot.", "Recruiter workspace")
    job_id = api.job_picker()
    if not job_id:
        return
    cfg = api.config() or {}
    apps = [a for a in (api.call("GET", f"/jobs/{job_id}/applications") or []) if a["resume_score"] is not None]
    st.session_state.setdefault("sched_msgs", {})
    shortlist_section(job_id, apps, cfg)
    schedule_section(job_id, apps)
    calendar_section(job_id)


def shortlist_section(job_id, apps, cfg):
    C.section("1. Shortlist", "The system proposes the top candidates; you decide who is shortlisted.")
    if not apps:
        C.empty_state("No scored candidates", "Score resumes on the Candidates page first.")
        st.button("Go to Candidates", on_click=api.go, args=("Candidates",))
        return
    top_n = (cfg.get("shortlist") or {}).get("top_n", 3)
    current = [a["application_id"] for a in apps if a["shortlisted"]]
    default = current or [a["application_id"] for a in apps[:top_n]]
    name = lambda i: next(f"{a['name'] or 'Application'} - score {a['resume_score']:.1f} (rank {a['rank']})" for a in apps if a["application_id"] == i)
    chosen = st.multiselect("Shortlisted candidates", [a["application_id"] for a in apps], default=default, format_func=name, key=f"sl_{job_id}")
    locked = [a for a in apps if a["application_id"] not in chosen and a["status"] not in ("SCORED", "SHORTLISTED")]
    if locked:
        st.caption("Candidates already past scheduling cannot be removed from the shortlist.")
    if st.button("Confirm shortlist", type="primary"):
        if api.call("POST", f"/jobs/{job_id}/shortlist", json={"application_ids": chosen}):
            api.flash("success", "Shortlist saved", f"{len(chosen)} candidate(s) shortlisted. Schedule them in step 2.")
            st.rerun()


def schedule_section(job_id, apps):
    C.section("2. Schedule interviews", "Each shortlisted candidate gets the earliest free slot. The backend refuses double bookings.")
    pending = [a for a in apps if a["status"] == "SHORTLISTED"]
    if pending:
        C.callout("info", f"{len(pending)} shortlisted candidate(s) need a slot", ", ".join(a["name"] or f"#{a['application_id']}" for a in pending))
    if st.button("Schedule shortlisted candidates", type="primary", disabled=not pending):
        with st.spinner("Finding free slots..."):
            res = api.call("POST", f"/jobs/{job_id}/schedule")
        for r in res or []:
            if r["scheduled"]:
                C.callout("success", f"{r['candidate']} is booked", f"{H.fmt_dt(r['start'])} on {r['resource']}.")
            else:
                C.callout("warning", f"Application #{r['application_id']} was not scheduled", f"{r['reason']}. Use 'Generate slots' in the calendar below, then try again.")
    C.callout("info", "About confirmations", "A confirmation JSON and e-mail text are saved on this computer for each booking. "
              "No e-mail is sent - give each candidate their access token yourself.")


def calendar_section(job_id):
    C.section("3. Scheduled interviews and calendar")
    slots = api.call("GET", "/slots") or []
    apps = {a["application_id"]: a for a in (api.call("GET", f"/jobs/{job_id}/applications") or [])}
    booked = [s for s in slots if s["application_id"] in apps]
    if not slots:
        C.empty_state("No calendar loaded", "Generate interview slots for the next working days, or load the mock calendar file.")
        c1, c2 = st.columns(2)
        if c1.button("Generate upcoming slots", type="primary"):
            if api.call("POST", "/calendar/generate") is not None:
                st.rerun()
        if c2.button("Load mock calendar file"):
            if api.call("POST", "/calendar/load") is not None:
                st.rerun()
        return
    if booked:
        C.table([("when", "When", "strong"), ("who", "Candidate"), ("room", "Resource"), ("status", "Status"), ("conf", "Confirmation file")],
                [{"when": H.fmt_dt(s["start"]), "who": s["candidate"] or "-", "room": s["resource"], "status": C.status_badge(s["application_status"]),
                  "conf": C.badge("Saved locally", "success", dot=False) if s["confirmation_file"] else C.badge("Missing", "warning", dot=False)}
                 for s in booked])
        with st.expander("Candidate access tokens (share privately with each candidate)"):
            show = st.checkbox("Reveal tokens")
            for s in booked:
                a = apps[s["application_id"]]
                st.markdown(f"**{a['name'] or '#' + str(a['application_id'])}** - `{a['access_token'] if show else '************'}`")
    else:
        C.empty_state("No interviews scheduled for this job", "Shortlist candidates and schedule them above.")
    free = [s for s in slots if s["application_id"] is None and s["start"] >= datetime.now().isoformat()]
    st.markdown(f"**Calendar availability:** {len(free)} upcoming free slot(s) of {len(slots)} total")
    if not free:
        C.callout("warning", "No upcoming free slots", "New candidates cannot be scheduled until more slots exist.")
    if st.button("Generate slots for the next 5 working days"):
        n = api.call("POST", "/calendar/generate")
        if n is not None:
            api.flash("success", "Calendar updated", f"{n['slots_added']} new slot(s) added." if n["slots_added"] else "Slots already exist for the next 5 working days.")
            st.rerun()
    days = sorted({s["start"][:10] for s in slots})
    pick = st.selectbox("View a day", days, format_func=lambda d: date.fromisoformat(d).strftime("%A %d %B %Y"))
    day = [s for s in slots if s["start"].startswith(pick)]
    C.table([("t", "Time", "strong"), ("room", "Resource"), ("state", "State")],
            [{"t": f"{H.fmt_dt(s['start'], False)} - {H.fmt_dt(s['end'], False)}", "room": s["resource"],
              "state": C.badge(f"Booked: {s['candidate']}", "info", dot=False) if s["application_id"] else C.badge("Free", "success", dot=False)} for s in day])
