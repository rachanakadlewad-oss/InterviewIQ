from datetime import date, datetime

import streamlit as st

from .. import api, components as C, helpers as H


def render():
    C.page_header("Shortlist & Scheduling", "Confirm who moves forward, then book each candidate into a free interview slot.", "Recruiter workspace")
    job_id = api.job_picker()
    if not job_id:
        return
    job = api.call("GET", f"/jobs/{job_id}") or {}
    job_title = job.get("title", f"Job #{job_id}")
    cfg = api.config() or {}
    apps = [a for a in (api.call("GET", f"/jobs/{job_id}/applications") or []) if a["resume_score"] is not None]
    st.session_state.setdefault("sched_msgs", {})
    shortlist_section(job_id, job_title, apps, cfg)
    schedule_section(job_id, apps, job_title)
    calendar_section(job_id)


def shortlist_section(job_id: int, job_title: str, apps: list, cfg: dict):
    C.section("1. Shortlist", "Review scored candidates, customize your selection, and confirm the shortlist to advance them to scheduling.")
    if not apps:
        C.empty_state("No scored candidates", "Score resumes on the Candidates page first.")
        st.button("Go to Candidates", on_click=api.go, args=("Candidates",))
        return

    # 1. Sort strictly in descending order of resume score
    sorted_apps = H.sort_candidates_by_score(apps)
    selectable_apps = [a for a in sorted_apps if a["status"] in ("SCORED", "SHORTLISTED")]
    locked_apps = [a for a in sorted_apps if a["status"] not in ("SCORED", "SHORTLISTED")]

    # 2. Consistent state management across page refreshes
    sel_key = f"sl_selected_{job_id}"
    confirmed_in_db = H.get_confirmed_shortlist_ids(selectable_apps)
    if sel_key not in st.session_state:
        # Initialise directly from confirmed database records (never auto-shortlist unconfirmed candidates)
        st.session_state[sel_key] = list(confirmed_in_db)

    selected_ids = list(dict.fromkeys(st.session_state[sel_key]))
    top_n = (cfg.get("shortlist") or {}).get("top_n", 3)

    # 3. Toolbar & live counter
    num_selected = len(selected_ids)
    num_selectable = len(selectable_apps)

    t_col1, t_col2, t_col3, t_col4 = st.columns([2.5, 1.2, 1.2, 1])
    with t_col1:
        st.markdown(
            f'<div class="iq-sl-pill"><i></i><span>Selected: <b>{num_selected}</b> of {num_selectable} candidates</span></div>'
            f'<span style="font-size:0.78rem;color:var(--muted);margin-left:0.6rem">Target: top {top_n}</span>',
            unsafe_allow_html=True
        )
    with t_col2:
        if st.button(f"Select top {top_n}", key=f"btn_top_{job_id}", help=f"Quickly select the top {top_n} candidates by score"):
            top_ids = [a["application_id"] for a in selectable_apps[:top_n]]
            st.session_state[sel_key] = list(dict.fromkeys(top_ids))
            st.rerun()
    with t_col3:
        if st.button("Select all", key=f"btn_all_{job_id}"):
            st.session_state[sel_key] = [a["application_id"] for a in selectable_apps]
            st.rerun()
    with t_col4:
        if st.button("Clear", key=f"btn_clear_{job_id}", help="Clear selection"):
            st.session_state[sel_key] = []
            st.rerun()

    # 4. Candidate cards list
    for a in sorted_apps:
        aid = a["application_id"]
        is_locked = a["status"] not in ("SCORED", "SHORTLISTED")
        is_selected = aid in selected_ids

        c_info, c_btn = st.columns([4.4, 1.2])
        with c_info:
            C._emit(C.candidate_card_html(a, job_title, is_selected=is_selected, is_locked=is_locked))
        with c_btn:
            if is_locked:
                st.caption("🔒 Scheduled")
            elif is_selected:
                if st.button("✕ Remove", key=f"btn_rem_{job_id}_{aid}", use_container_width=True):
                    st.session_state[sel_key] = H.remove_candidate_from_selection(st.session_state[sel_key], aid)
                    st.rerun()
            else:
                if st.button("➕ Add", key=f"btn_add_{job_id}_{aid}", type="secondary", use_container_width=True):
                    st.session_state[sel_key] = H.add_candidate_to_selection(st.session_state[sel_key], aid)
                    st.rerun()

    # 5. Summary & Confirmation Area
    st.markdown('<div class="iq-sl-confirm-box">', unsafe_allow_html=True)
    st.markdown(f"#### Shortlist Confirmation for {job_title}")

    has_unconfirmed_changes = set(selected_ids) != set(confirmed_in_db)
    if num_selected == 0:
        C.callout("neutral", "No candidates selected",
                  f"Click '➕ Add' on any candidate card above or use 'Select top {top_n}' to build your shortlist.")
    else:
        names_summary = ", ".join(
            f"**{a['name'] or a['application_id']}** ({a['resume_score']:.1f}/10)"
            for a in selectable_apps if a["application_id"] in selected_ids
        )
        st.markdown(f"**{num_selected} candidate(s) ready to confirm:** {names_summary}")
        if has_unconfirmed_changes:
            st.caption("⚠️ Changes staged in this view require confirmation before candidates become eligible for interview scheduling.")

    b_col1, b_col2 = st.columns([2, 1])
    with b_col1:
        if st.button("Confirm shortlist", type="primary", use_container_width=True, key=f"btn_confirm_{job_id}"):
            valid, errors = H.validate_shortlist_selection(selected_ids, selectable_apps)
            if not valid:
                for err in errors:
                    C.callout("error", "Validation error", err)
            else:
                res = api.call("POST", f"/jobs/{job_id}/shortlist", json={"application_ids": selected_ids})
                if res is not None:
                    api.flash("success", "Shortlist Confirmed",
                              f"Successfully shortlisted {len(selected_ids)} candidate(s) for '{job_title}'. "
                              f"You can now schedule their interviews in Step 2 below.")
                    st.rerun()

    with b_col2:
        if confirmed_in_db:
            if st.button("Reset shortlist", use_container_width=True, key=f"btn_reset_{job_id}", help="Un-shortlist all candidates and return them to Scored status"):
                res = api.call("POST", f"/jobs/{job_id}/shortlist", json={"application_ids": []})
                if res is not None:
                    st.session_state[sel_key] = []
                    api.flash("info", "Shortlist Reset", f"Shortlist for '{job_title}' was reset. All candidates returned to Scored status.")
                    st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


def schedule_section(job_id, apps, job_title="Position"):
    C.section("2. Schedule Interviews", "Each confirmed shortlisted candidate gets the earliest free slot. The backend refuses double bookings.")
    with st.container(border=True):
        pending = [a for a in apps if a["status"] == "SHORTLISTED"]
        if pending:
            C.callout("info", f"{len(pending)} confirmed candidate(s) need an interview slot",
                      ", ".join(a["name"] or f"#{a['application_id']}" for a in pending))
        else:
            st.caption("No pending shortlisted candidates need scheduling right now.")

        if st.button("Schedule shortlisted candidates", type="primary", disabled=not pending, key=f"btn_sched_{job_id}", use_container_width=True):
            with st.spinner("Assigning earliest available slots..."):
                res = api.call("POST", f"/jobs/{job_id}/schedule")

            booked_msgs = []
            failed_msgs = []
            for r in res or []:
                cand_name = r.get("candidate") or f"Application #{r['application_id']}"
                if r.get("scheduled"):
                    if not r.get("already_scheduled"):
                        booked_msgs.append(f"{cand_name} on {H.fmt_dt(r['start'])} ({r['resource']})")
                else:
                    failed_msgs.append(f"{cand_name}: {r.get('reason', 'no free slot available')}")

            if booked_msgs:
                api.flash("success", "Interviews Booked",
                          f"Successfully scheduled {len(booked_msgs)} candidate(s): " + ", ".join(booked_msgs))
            if failed_msgs:
                api.flash("warning", "Insufficient Availability",
                          f"Could not schedule {len(failed_msgs)} candidate(s): " + "; ".join(failed_msgs) +
                          ". Generate more slots in the calendar below, then click Schedule again.")

            st.rerun()

        C.callout("info", "About booking confirmations", "A confirmation JSON and e-mail text are saved locally for each booking. "
                  "Give each candidate their access token from the table below to allow them to access their interview portal.")



def calendar_section(job_id):
    C.section("3. Scheduled interviews and calendar")
    slots = api.call("GET", "/slots") or []
    apps_list = api.call("GET", f"/jobs/{job_id}/applications") or []
    apps = {a["application_id"]: a for a in apps_list}
    booked_for_job = [s for s in slots if s["application_id"] in apps]

    if not slots:
        C.empty_state("No calendar loaded", "Generate interview slots for the next working days, or load the mock calendar file.")
        c1, c2 = st.columns(2)
        if c1.button("Generate upcoming slots", type="primary"):
            if api.call("POST", "/calendar/generate") is not None:
                api.flash("success", "Slots Generated", "Created interview slots for the next 5 working days.")
                st.rerun()
        if c2.button("Load mock calendar file"):
            if api.call("POST", "/calendar/load") is not None:
                api.flash("success", "Mock Calendar Loaded", "Loaded interview slots from mock calendar.")
                st.rerun()
        return

    # 1. Scheduled Interviews Table for this Job
    with st.container(border=True):
        st.markdown("#### Scheduled Interviews (This Job)")
        if booked_for_job:
            C.table([("when", "When", "strong"), ("who", "Candidate"), ("room", "Resource"), ("status", "Status"), ("conf", "Confirmation file")],
                    [{"when": H.fmt_dt(s["start"]), "who": s["candidate"] or "-", "room": s["resource"], "status": C.status_badge(s["application_status"]),
                      "conf": C.badge("Saved locally", "success", dot=False) if s["confirmation_file"] else C.badge("Missing", "warning", dot=False)}
                     for s in booked_for_job])
            with st.expander("Candidate access tokens (share privately with each candidate)"):
                show = st.checkbox("Reveal tokens")
                for s in booked_for_job:
                    a = apps.get(s["application_id"])
                    if a:
                        st.markdown(f"**{a['name'] or '#' + str(a['application_id'])}** - `{a['access_token'] if show else '************'}`")
        else:
            C.empty_state("No interviews scheduled for this job", "Shortlist candidates in Step 1 and schedule them in Step 2 above.", icon="📅")

    # 2. Calendar Availability Metrics & Daily Schedule
    with st.container(border=True):
        now_iso = datetime.now().isoformat()
        upcoming_slots = [s for s in slots if s["start"] >= now_iso]
        free_upcoming = [s for s in upcoming_slots if s["application_id"] is None]
        booked_upcoming = [s for s in upcoming_slots if s["application_id"] is not None]

        st.markdown("#### Calendar Capacity & Daily Schedule")
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            st.markdown(
                f'<div class="iq-sl-pill"><i></i><span>Upcoming Free Slots: <b>{len(free_upcoming)}</b></span></div>',
                unsafe_allow_html=True
            )
        with m_col2:
            st.markdown(
                f'<div class="iq-sl-pill"><span style="color:var(--primary)">●</span>&nbsp;<span>Booked Interviews: <b>{len(booked_upcoming)}</b></span></div>',
                unsafe_allow_html=True
            )
        with m_col3:
            st.markdown(
                f'<div class="iq-sl-pill"><span style="color:var(--muted)">■</span>&nbsp;<span>Total Upcoming Slots: <b>{len(upcoming_slots)}</b></span></div>',
                unsafe_allow_html=True
            )

        if not free_upcoming:
            C.callout("warning", "No upcoming free slots available",
                      "All upcoming slots are either booked or in the past. Generate more slots below to enable interview bookings.")

        if st.button("Generate slots for the next 5 working days", key="btn_gen_5d", use_container_width=True):
            n = api.call("POST", "/calendar/generate")
            if n is not None:
                api.flash("success", "Calendar updated",
                          f"{n['slots_added']} new slot(s) added." if n["slots_added"] else "Slots already exist for the next 5 working days (no duplicates created).")
                st.rerun()

        # 3. Daily Calendar View
        days = sorted({s["start"][:10] for s in slots})
        if days:
            st.markdown("##### Day Schedule Breakdown")
            pick = st.selectbox("View day schedule", days, format_func=lambda d: date.fromisoformat(d).strftime("%A %d %B %Y"), key="cal_pick_day")
            raw_day_slots = [s for s in slots if s["start"].startswith(pick)]
            dedup_map = {}
            for s in raw_day_slots:
                key = (s["resource"], s["start"], s["end"])
                if key not in dedup_map or (s.get("application_id") and not dedup_map[key].get("application_id")):
                    dedup_map[key] = s
            day_slots = list(dedup_map.values())
            day_slots.sort(key=lambda s: (s["start"], s["resource"], s["id"]))
            C.table([("t", "Time", "strong"), ("room", "Resource"), ("state", "State"), ("job", "Job Position")],
                    [{"t": f"{H.fmt_dt(s['start'], False)} - {H.fmt_dt(s['end'], False)}", "room": s["resource"],
                      "state": C.badge(f"Booked: {s['candidate']}", "info", dot=False) if s["application_id"] else C.badge("Free", "success", dot=False),
                      "job": s.get("job_title") or ("-" if not s["application_id"] else "Other Job")}
                     for s in day_slots])

