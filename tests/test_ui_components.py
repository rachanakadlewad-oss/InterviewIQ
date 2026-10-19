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
