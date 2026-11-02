from frontend.iqui import components as C


def test_user_text_is_escaped_everywhere():
    evil = '<script>alert(1)</script><img src=x onerror=1>'
    assert "<script>" not in C.badge(evil)
    assert "<script>" not in C.table_html([("n", "Name")], [{"n": evil}])
    assert "<script>" not in C.quote_html(evil)
    assert "<script>" not in C.kv_html([("k", evil)])
    assert "<script>" not in C.metric_html([{"label": evil, "value": evil, "hint": evil}])
    assert "<script>" not in C.callout_html("info", evil, evil)
    assert "<script>" not in C.trace_html([{"turn": 1, "decision": "NEXT_COMPETENCY", "competency": evil, "trigger_phrase": evil,
                                           "reasoning": evil, "question_asked": evil, "source": "llm", "guard_note": evil, "agent_decision": "CONCLUDE"}])


def test_raw_fragments_are_not_double_escaped():
    out = C.table_html([("s", "Status")], [{"s": C.status_badge("SCORED")}])
    assert 'class="iq-badge info"' in out and "&lt;span" not in out


def test_empty_table_shows_empty_state():
    assert "iq-empty" in C.table_html([("a", "A")], [], "No candidates yet")


def test_funnel_widths_are_relative_and_safe_for_zero():
    h = C.funnel_html([{"stage": "A", "count": 10}, {"stage": "B", "count": 5}])
    assert "width:100%" in h and "width:50%" in h
    assert "width:0%" in C.funnel_html([{"stage": "A", "count": 0}])


def test_score_bar_handles_none_and_clamps():
    assert "not covered" in C.score_bar(None)
    assert "width:100%" in C.score_bar(15) and "width:0%" in C.score_bar(-3)


def test_compact_output_has_no_blank_or_indented_lines():
    s = C._compact("<div>\n    <p>x</p>\n\n   </div>")
    assert "\n" not in s


def test_demo_source_is_labelled_distinct_from_llm():
    assert "Demo rules" in C.source_badge("demo_rules") and ">LLM<" in C.source_badge("llm")


def test_trace_shows_guard_override_and_original_proposal():
    h = C.trace_html([{"turn": 3, "decision": "NEXT_COMPETENCY", "competency": "python", "trigger_phrase": "x", "reasoning": "y",
                       "question_asked": "q?", "source": "guard", "guard_note": "follow-up limit reached", "agent_decision": "NARROW_FOLLOW_UP"}])
    assert "follow-up limit reached" in h and "Narrow follow-up" in h


def test_emit_uses_streamlit_markdown_with_unsafe_html():
    import sys, types
    calls = []
    fake = types.SimpleNamespace(markdown=lambda s, unsafe_allow_html=False: calls.append((s, unsafe_allow_html)))
    sys.modules["streamlit"] = fake
    try:
        C.page_header("Title", "Sub", "Eyebrow")
    finally:
        del sys.modules["streamlit"]
    assert calls and calls[0][1] is True and "Title" in calls[0][0]


def test_dollar_signs_are_neutralised_for_markdown_math():
    assert "$" not in C.esc("costs $5 and $10")
    assert C.esc("a & b") == "a &amp; b"


def test_trace_shows_readable_competency_names():
    t = [{"turn": 1, "decision": "BROAD_PIVOT", "competency": "extra_incident_response", "trigger_phrase": "x", "reasoning": "y", "question_asked": "q?", "source": "llm"},
         {"turn": 2, "decision": "NEXT_COMPETENCY", "competency": "api_design", "trigger_phrase": "x", "reasoning": "y", "question_asked": "q?", "source": "llm"}]
    h = C.trace_html(t, {"api_design": "REST API Design"})
    assert "Incident Response" in h and "REST API Design" in h and "extra_" not in h and "api_design" not in h


def test_competency_evidence_html_renders_all_requested_sections():
    info = {
        "name": "System Design",
        "description": "Architecting scalable systems",
        "weight": 1.5,
        "score": 6.2,
        "level_label": "Partial evidence",
        "level_tone": "warning",
        "evidence": ["Built distributed microservices in Go handling 2,000 requests/sec."],
        "relevance_explanation": "Demonstrates practical API microservices experience but lacks multi-region failover.",
        "demonstrated_points": ["Referenced microservices and Go.", "Verified throughput: 2,000 requests/sec."],
        "missing_points": ["No multi-region architecture or disaster recovery verified."],
        "suggested_questions": [
            {"tag": "Primary Domain Question", "question": "Walk me through how you designed the distributed services."},
            {"tag": "Targeted Production Probe", "question": "How did you handle service discovery and network partitions?"}
        ]
    }
    html = C.competency_evidence_html(info)

    # 1. Competency name & score out of 10
    assert "System Design" in html
    assert "6.2" in html
    assert "/ 10" in html

    # 2. Competency weight
    assert "Weight 1.5x" in html

    # 3. Evidence found in the resume
    assert "Built distributed microservices in Go" in html

    # 4. Explanation of why evidence is relevant
    assert "Demonstrates practical API microservices experience" in html

    # 5. Whether evidence is strong, partial or missing
    assert "Partial evidence" in html

    # 6. Skills or experience that are not demonstrated
    assert "Demonstrated in Resume" in html
    assert "Not Demonstrated / Gaps to Probe" in html
    assert "No multi-region architecture" in html

    # 7. Suggested interview questions
    assert "Suggested Interview Validation Probes" in html
    assert "Walk me through how you designed the distributed services." in html
    assert "service discovery and network partitions" in html


def test_competency_evidence_html_handles_missing_evidence():
    info = {
        "name": "Kubernetes & Cloud",
        "description": "Cluster management",
        "weight": 1.0,
        "score": 0.0,
        "level_label": "Missing evidence",
        "level_tone": "neutral",
        "evidence": [],
        "relevance_explanation": "No relevant evidence was identified in the resume text for Kubernetes & Cloud.",
        "demonstrated_points": ["No relevant skills, projects, or responsibilities cited in resume."],
        "missing_points": ["Missing core domain technologies: k8s, helm, terraform."],
        "suggested_questions": [
            {"tag": "Primary Domain Question", "question": "Have you worked with Kubernetes in any role?"}
        ]
    }
    html = C.competency_evidence_html(info)
    assert "Kubernetes &amp; Cloud" in html
    assert "0.0" in html
    assert "Missing evidence" in html
    assert "No direct mentions, responsibilities, or projects related to this competency were identified" in html
    assert "No relevant evidence was identified in the resume text" in html
    assert "Have you worked with Kubernetes in any role?" in html


def test_candidate_card_html_renders_fields_and_states():
    cand = {
        "application_id": 42,
        "name": "Aarav Mehta",
        "email": "aarav@example.com",
        "rank": 1,
        "resume_score": 8.5,
        "status": "SCORED",
        "shortlisted": False
    }
    # Test selected card
    html = C.candidate_card_html(cand, "Senior Backend Engineer", is_selected=True, is_locked=False)
    assert "Aarav Mehta" in html
    assert "aarav@example.com" in html
    assert "Senior Backend Engineer" in html
    assert "Rank #1" in html
    assert "8.5" in html
    assert "/ 10" in html
    assert "is-selected" in html
    assert "Selected (Pending Confirmation)" in html

    # Test confirmed shortlisted card
    cand_shortlisted = {**cand, "shortlisted": True}
    html_short = C.candidate_card_html(cand_shortlisted, "Senior Backend Engineer", is_selected=False, is_locked=False)
    assert "Shortlist Confirmed" in html_short

    # Test locked/scheduled card
    html_locked = C.candidate_card_html(cand, "Senior Backend Engineer", is_selected=False, is_locked=True)
    assert "is-locked" in html_locked
    assert "Interview Scheduled" in html_locked
