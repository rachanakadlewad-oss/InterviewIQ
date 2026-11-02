"""Reusable UI building blocks. Builders return HTML strings; `_emit` writes them with st.markdown.
Everything user-supplied (candidate names, resume excerpts, answers) is HTML-escaped."""
import html
import re
from typing import Iterable, List, Optional

from . import helpers as H


class Raw(str):
    """Marks an already-safe HTML fragment."""


def esc(x) -> str:
    # '$' is escaped too: Streamlit markdown would otherwise try to render $...$ as math
    return html.escape("" if x is None else str(x)).replace("$", "&#36;")


def _cell(v) -> str:
    return v if isinstance(v, Raw) else esc(v)


def _compact(s: str) -> str:
    # Streamlit's markdown treats indented/blank lines inside HTML as code blocks -> emit one compact line
    return re.sub(r"\n\s*", "", s).strip()


def _emit(s: str):
    import streamlit as st
    st.markdown(_compact(s), unsafe_allow_html=True)


# ------------------------------------------------------------------ builders (pure)
def badge(text, tone: str = "neutral", dot: bool = True) -> Raw:
    return Raw(f'<span class="iq-badge {esc(tone)}">{"<i></i>" if dot else ""}{esc(text)}</span>')


def status_badge(status: str) -> Raw:
    label, tone = H.status_label(status)
    return badge(label, tone)


def source_badge(src) -> Raw:
    label, tone = H.source_label(src)
    return badge(label, tone, dot=False)


def score_bar(value: Optional[float], max_value: float = 10.0) -> Raw:
    if value is None:
        return Raw('<span style="color:var(--muted)">not covered</span>')
    pct = max(0.0, min(100.0, value / max_value * 100))
    tone = H.score_tone(value, max_value)
    return Raw(f'<div class="iq-bar"><div class="track"><div class="fill {tone}" style="width:{pct:.0f}%"></div></div>'
               f'<span>{value:.1f}</span></div>')


def table_html(columns: List[tuple], rows: List[dict], empty: str = "Nothing to show yet.") -> str:
    """columns: (key, label[, 'r'|'strong'])"""
    if not rows:
        return empty_html("No data", empty)
    head = "".join(f'<th class="{c[2] if len(c) > 2 and c[2] == "r" else ""}">{esc(c[1])}</th>' for c in columns)
    body = ""
    for r in rows:
        tds = ""
        for c in columns:
            cls = c[2] if len(c) > 2 else ""
            tds += f'<td class="{cls}">{_cell(r.get(c[0], ""))}</td>'
        body += f"<tr>{tds}</tr>"
    return f'<div class="iq-tablewrap"><table class="iq-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def empty_html(title: str, body: str = "") -> str:
    return f'<div class="iq-empty"><div class="t">{esc(title)}</div><div class="b">{esc(body)}</div></div>'


def callout_html(tone: str, title: str, body: str = "") -> str:
    return (f'<div class="iq-callout {esc(tone)}"><div><div class="t">{esc(title)}</div>'
            f'{f"<div class=b>{esc(body)}</div>" if body else ""}</div></div>')


def metric_html(items: Iterable[dict]) -> str:
    cards = ""
    for it in items:
        cards += (f'<div class="iq-metric tone-{esc(it.get("tone", "neutral"))}"><div class="l">{esc(it["label"])}</div>'
                  f'<div class="v">{esc(it["value"])}</div><div class="h">{esc(it.get("hint", ""))}</div></div>')
    return f'<div class="iq-grid">{cards}</div>'


def funnel_html(stages: List[dict]) -> str:
    top = max([s["count"] for s in stages] + [1])
    rows = "".join(f'<div class="iq-frow"><span>{esc(s["stage"])}</span><div class="iq-ftrack"><div class="iq-ffill" '
                   f'style="width:{s["count"] / top * 100:.0f}%"></div></div><span class="n">{s["count"]}</span></div>' for s in stages)
    return f'<div class="iq-funnel">{rows}</div>'


def stepper_html(steps: List[tuple]) -> str:
    out = ""
    for i, (label, state) in enumerate(steps, 1):
        word = {"done": "Done", "current": "Next", "todo": "Later"}[state]
        out += f'<div class="iq-step {state}"><div class="n">{i}. {word}</div>{esc(label)}</div>'
    return f'<div class="iq-stepper">{out}</div>'


def kv_html(pairs: List[tuple]) -> str:
    return '<div class="iq-kv">' + "".join(
        f'<div><div class="k">{esc(k)}</div><div class="v">{_cell(v) if v not in (None, "") else "-"}</div></div>' for k, v in pairs) + "</div>"


def quote_html(text: str) -> str:
    return f'<div class="iq-quote">{esc(text)}</div>'


def pretty_competency(cid: str, names: Optional[dict] = None) -> str:
    if names and cid in names:
        return names[cid]
    return cid.replace("extra_", "").replace("_", " ").strip().title() or cid


def trace_html(trace: List[dict], names: Optional[dict] = None) -> str:
    """Concise, auditable decision explanation per turn. Shows the stored 1-2 sentence rationale, not model internals."""
    items = ""
    for t in trace:
        dec = t["decision"]
        src_label, src_tone = H.source_label(t.get("source"))
        override = ""
        if t.get("guard_note"):
            was = H.DECISION_LABEL.get(t.get("agent_decision") or "", t.get("agent_decision") or "")
            override = (f'<div class="row"><b>Supervisor guard:</b> {esc(t["guard_note"])}'
                        f'{f" (agent proposed: {esc(was)})" if was else ""}</div>')
        q = (f'<div class="row"><b>Question asked:</b> {esc(t["question_asked"])}</div>' if t.get("question_asked") else "")
        items += (f'<div class="iq-turn"><div class="top"><span>Turn {t["turn"]}</span>'
                  f'{badge(H.DECISION_LABEL.get(dec, dec), H.DECISION_TONE.get(dec, "neutral"))}'
                  f'{badge(src_label, src_tone, dot=False)}<span>Competency: {esc(pretty_competency(t["competency"], names))}</span></div>'
                  f'<div class="row"><b>Trigger:</b> {esc(t["trigger_phrase"])}</div>'
                  f'<div class="row"><b>Why:</b> {esc(t["reasoning"])}</div>{override}{q}</div>')
    return f'<div class="iq-trace">{items}</div>'


# ------------------------------------------------------------------ emitters (Streamlit)
def inject_theme():
    from .theme import css_block
    _emit(css_block())


def brand():
    _emit('<div class="iq-brand"><div class="iq-logo">IQ</div><div><div class="iq-brand-name">InterviewIQ</div>'
          '<div class="iq-brand-sub">Agentic hiring platform</div></div></div>')


def side_label(text: str):
    _emit(f'<div class="iq-side-label">{esc(text)}</div>')


def page_header(title: str, subtitle: str = "", eyebrow: str = ""):
    _emit(f'<div class="iq-header">{f"<div class=iq-eyebrow>{esc(eyebrow)}</div>" if eyebrow else ""}'
          f'<h1 class="iq-title">{esc(title)}</h1>{f"<p class=iq-subtitle>{esc(subtitle)}</p>" if subtitle else ""}</div>')


def section(title: str, caption: str = ""):
    _emit(f'<div class="iq-section"><h3>{esc(title)}</h3>{f"<p>{esc(caption)}</p>" if caption else ""}</div>')


def callout(tone: str, title: str, body: str = ""):
    _emit(callout_html(tone, title, body))


def empty_state(title: str, body: str = ""):
    _emit(empty_html(title, body))


def metric_grid(items):
    _emit(metric_html(items))


def funnel(stages):
    _emit(funnel_html(stages))


def stepper(steps):
    _emit(stepper_html(steps))


def table(columns, rows, empty="Nothing to show yet."):
    _emit(table_html(columns, rows, empty))


def kv(pairs):
    _emit(kv_html(pairs))


def quote(text):
    _emit(quote_html(text))


def trace(entries, names=None):
    _emit(trace_html(entries, names))


def question_card(label: str, text: str):
    _emit(f'<div class="iq-question"><div class="l">{esc(label)}</div><div class="q">{esc(text)}</div></div>')


def badges(*bs):
    _emit('<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin:.2rem 0 .8rem">' + "".join(bs) + "</div>")


def competency_evidence_html(info: dict) -> str:
    weight_pill = f'<span class="iq-badge neutral">Weight {info["weight"]:.1f}x</span>'
    lvl_badge = badge(info["level_label"], info["level_tone"], dot=True)
    score_pill = f'<div class="iq-comp-score" style="font-weight:700;font-size:1.15rem;color:var(--text)">{info["score"]:.1f} <small style="font-size:0.75rem;color:var(--muted)">/ 10</small></div>'
    pct = max(0.0, min(100.0, info["score"] / 10.0 * 100))
    bar_html = f'<div class="iq-bar" style="min-width:130px"><div class="track"><div class="fill {info["level_tone"]}" style="width:{pct:.0f}%"></div></div><span>{info["score"]:.1f}</span></div>'

    desc_html = f'<div class="iq-comp-desc">{esc(info["description"])}</div>' if info.get("description") else ""
    top = (f'<div class="iq-comp-top">'
           f'<div style="flex:1"><div class="iq-comp-title">{esc(info["name"])}</div>{desc_html}</div>'
           f'<div style="display:flex;flex-direction:column;align-items:flex-end;gap:0.35rem">'
           f'<div style="display:flex;gap:0.4rem;align-items:center;flex-wrap:wrap">{weight_pill}{lvl_badge}{score_pill}</div>'
           f'{bar_html}</div></div>')

    # 1. Verbatim Evidence
    ev_body = ""
    if info["evidence"]:
        for e in info["evidence"]:
            ev_body += f'<div class="iq-ev-card">"{esc(e)}"</div>'
    else:
        ev_body = f'<div class="iq-ev-empty">No direct mentions, responsibilities, or projects related to this competency were identified in the resume text.</div>'
    sec_evidence = f'<div class="iq-card-title accent">📄 Verbatim Resume Evidence</div>{ev_body}'

    # 2. Relevance & Scoring Rationale
    sec_rationale = (f'<div class="iq-card-title accent">🔍 Relevance & Score Rationale</div>'
                     f'<div class="iq-rationale-box">{esc(info["relevance_explanation"])}</div>')

    # 3. Gap Analysis (Demonstrated vs Not Demonstrated)
    dem_items = "".join(f'<li class="iq-gap-item"><i>✓</i><span>{esc(p)}</span></li>' for p in info["demonstrated_points"])
    mis_items = "".join(f'<li class="iq-gap-item"><i>✗</i><span>{esc(p)}</span></li>' for p in info["missing_points"])
    sec_gap = (f'<div class="iq-card-title accent">⚖️ Demonstrated vs. Not Demonstrated</div>'
               f'<div class="iq-gap-grid">'
               f'<div class="iq-gap-col demonstrated"><div style="font-weight:600;font-size:0.82rem;color:var(--success);margin-bottom:0.5rem">✅ Demonstrated in Resume</div><ul class="iq-gap-list">{dem_items}</ul></div>'
               f'<div class="iq-gap-col missing"><div style="font-weight:600;font-size:0.82rem;color:var(--warning);margin-bottom:0.5rem">⚠️ Not Demonstrated / Gaps to Probe</div><ul class="iq-gap-list">{mis_items}</ul></div>'
               f'</div>')

    # 4. Suggested Interview Probes
    q_items = ""
    for q in info["suggested_questions"]:
        q_items += (f'<div class="iq-probe-item">'
                    f'<div class="iq-probe-tag">{esc(q["tag"])}</div>'
                    f'<div class="iq-probe-q">"{esc(q["question"])}"</div>'
                    f'</div>')
    sec_probes = (f'<div class="iq-card-title accent">💡 Suggested Interview Validation Probes</div>'
                  f'<div class="iq-probe-box">'
                  f'<div style="font-size:0.78rem;color:var(--muted);margin-bottom:0.5rem">Use these tailored questions in the interview to validate candidate depth:</div>'
                  f'{q_items}</div>')

    return f'<div class="iq-comp-box">{top}{sec_evidence}{sec_rationale}{sec_gap}{sec_probes}</div>'


def competency_evidence_card(comp: dict, score_data: Optional[dict] = None):
    info = H.analyze_competency_details(comp, score_data)
    _emit(competency_evidence_html(info))


def candidate_card_html(cand: dict, job_title: str, is_selected: bool, is_locked: bool) -> str:
    name = esc(cand.get("name") or f"Candidate #{cand['application_id']}")
    email = esc(cand.get("email") or "No email provided")
    role = esc(job_title)
    rank = cand.get("rank")
    rank_str = f"Rank #{rank}" if rank is not None else "Rank -"
    score = cand.get("resume_score")
    score_val = f"{score:.1f}" if score is not None else "-"
    pct = max(0.0, min(100.0, (score or 0.0) / 10.0 * 100))
    tone = H.score_tone(score, 10.0)

    classes = ["iq-cand-card"]
    if is_selected:
        classes.append("is-selected")
    if is_locked:
        classes.append("is-locked")

    if is_locked:
        st_badge = badge("Interview Scheduled", "info", dot=True)
    elif cand.get("shortlisted"):
        st_badge = badge("Shortlist Confirmed", "success", dot=True)
    elif is_selected:
        st_badge = badge("Selected (Pending Confirmation)", "warning", dot=True)
    else:
        st_badge = badge("Scored", "neutral", dot=True)

    bar = (f'<div class="iq-bar" style="min-width:120px">'
           f'<div class="track"><div class="fill {tone}" style="width:{pct:.0f}%"></div></div>'
           f'<span>{score_val}</span></div>')

    return (f'<div class="{" ".join(classes)}">'
            f'<div class="iq-cand-top">'
            f'<div style="flex:1">'
            f'<div class="iq-cand-meta">'
            f'<span class="iq-rank-badge">{rank_str}</span>'
            f'<span class="iq-cand-name">{name}</span>'
            f'{st_badge}'
            f'</div>'
            f'<div class="iq-cand-role">Position: <b>{role}</b> &nbsp;·&nbsp; {email}</div>'
            f'</div>'
            f'<div class="iq-cand-scorebox">'
            f'<div class="iq-cand-score">{score_val} <small>/ 10</small></div>'
            f'{bar}'
            f'</div>'
            f'</div>'
            f'</div>')
