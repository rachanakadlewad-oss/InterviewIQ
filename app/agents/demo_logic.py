"""DETERMINISTIC DEMO-MODE implementations of the three agents.

!!  These are keyword/rule heuristics, NOT LLM reasoning. They exist so the whole pipeline can be demonstrated
!!  without an API key. Every output produced here is labelled source='demo_rules'. Real semantic reasoning
!!  only happens when LLM_PROVIDER is openai/anthropic (see recruitment.py / interviewer.py / assessment.py)."""
import re
from typing import Dict, List

from app.services.interview_engine import is_repeat
from app.textutil import truncate_words, word_count

ACTION_VERBS = r"\b(i|we)\s+(built|designed|implemented|led|wrote|deployed|reduced|improved|fixed|optimi[sz]ed|mentored|tested|migrated|created|automated|debugged|refactored)"

DEMO_ACTION_VERBS = re.compile(
    r"\b(designed|built|implemented|re-architected|rearchitected|developed|deployed|"
    r"reduced|improved|fixed|optimi[sz]ed|mentored|tested|migrated|created|automated|"
    r"debugged|refactored|led|managed|onboarded|tuned|authored|maintained|architected|"
    r"configured|monitored|investigated|profiled|owned|orchestrated|wrote|written|delivered|"
    r"established|cut|spearheaded|drove|scaled)\b",
    re.I
)

DEMO_INTRO_PASSIVE = re.compile(
    r"\b(learned|intern|college project|simple|basic|seeking|learning|student|"
    r"familiar with|elementary|coursework|academic project|minor project)\b",
    re.I
)

DEMO_MEASURABLE_METRIC = re.compile(
    r"(?:"
    r"\b\d+(?:\.\d+)?\s*%\s*(?:reduction|increase|improvement|coverage|faster|latency|stability)?\b|"
    r"\b\d[\d,]*\+?\s*(?:requests|req|qps|rps|users|concurrent|records|events|messages|tps)\s*(?:per\s*(?:sec|second|day|month)|/s)?\b|"
    r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds|seconds)\s*(?:latency|response|faster)?\b|"
    r"\b(?:team\s*of|led|managed|mentored)\s*(\d{1,2})\s*(?:engineers|developers|people|juniors|members)\b|"
    r"\b\d{1,3}\+?\s*(?:rest\s+api\s+|api\s+)?(?:endpoints|microservices|services|apis|pipelines|modules)\b"
    r")",
    re.I
)


def _extract_genuine_metrics(text: str) -> List[str]:
    hits = []
    for m in DEMO_MEASURABLE_METRIC.finditer(text):
        s = m.group(0).strip()
        # Avoid treating calendar years or pure numbers like phone numbers as metrics
        if not re.match(r"^(?:19|20)\d\d$", s) and not re.match(r"^\d{5,}$", s):
            hits.append(s)
    return hits


def _kw_hits(text: str, keywords: List[str]) -> List[str]:
    low = text.lower()
    return [k for k in keywords if re.search(r"\b" + re.escape(k.lower()), low)]


def _units(text: str) -> List[str]:
    """Lines and sentences (all exact substrings of the text)."""
    out = []
    for line in re.split(r"[\r\n]+", text):
        for s in re.split(r"(?<=[.!?])\s+", line):
            s = s.strip(" \t-\u2022*")
            if len(s) > 10:
                out.append(s)
    return out


# ------------------------------------------------------------------ recruitment
def demo_resume_scores(job: dict, resume_text: str) -> dict:
    from app.textutil import contains_quote
    units = _units(resume_text)
    scores = []
    for c in job["competencies"]:
        cid = c["id"]
        cname = c["name"]
        kws = c.get("keywords") or [c["name"]]

        matching_units = []
        all_hits = set()

        for u in units:
            hits = _kw_hits(u, kws)
            if hits:
                all_hits.update(h.lower() for h in hits)
                has_action = bool(DEMO_ACTION_VERBS.search(u))
                is_intro = bool(DEMO_INTRO_PASSIVE.search(u))
                metrics = _extract_genuine_metrics(u)
                matching_units.append({
                    "unit": u,
                    "hits": hits,
                    "has_action": has_action,
                    "is_intro": is_intro,
                    "metrics": metrics,
                })

        if not matching_units:
            scores.append({
                "competency_id": cid,
                "score": 0.0,
                "evidence": [],
                "evidence_level": "MISSING",
                "justification": f"[Demo Heuristic - Missing Evidence] No relevant skills, projects, or responsibilities found in the resume for {cname}."
            })
            continue

        # Sort matching units by relevance: direct action + metrics > direct action > intro > raw list
        matching_units.sort(
            key=lambda x: (
                bool(x["metrics"]),
                x["has_action"] and not x["is_intro"],
                len(x["hits"]),
                -len(x["unit"])
            ),
            reverse=True
        )

        has_direct_action = any(m["has_action"] and not m["is_intro"] for m in matching_units)
        direct_metrics = [metric for m in matching_units if m["has_action"] and not m["is_intro"] for metric in m["metrics"]]
        is_purely_intro_or_passive = not has_direct_action

        evidence = [m["unit"][:220] for m in matching_units[:3]]
        evidence = [e for e in evidence if contains_quote(resume_text, e)]
        if not evidence and matching_units:
            evidence = [matching_units[0]["unit"][:200]]

        if is_purely_intro_or_passive:
            # Partial evidence: mention in skills list or coursework/intern without production ownership
            evidence_level = "PARTIAL"
            any_intro = any(m["is_intro"] for m in matching_units)
            if any_intro:
                score = 3.5 + min(1.0, 0.3 * (len(all_hits) - 1))
                score = min(4.5, score)
                reason = f"Mentioned in introductory, coursework, or junior project context ({', '.join(sorted(all_hits)[:3])}) without demonstrated production responsibility or scale"
            else:
                score = 2.5 + min(0.8, 0.2 * (len(all_hits) - 1))
                score = min(3.5, score)
                reason = f"Referenced skills/tools ({', '.join(sorted(all_hits)[:3])}) without detailed project descriptions or measurable outcomes"

            justification = (
                f"[Demo Heuristic - Partial Evidence] {reason}. "
                f"Evaluated against rubric level 1-2."
            )
        else:
            # Direct evidence: demonstrated responsibilities
            evidence_level = "DIRECT"
            base_score = 6.0

            action_count = sum(1 for m in matching_units if m["has_action"] and not m["is_intro"])
            depth_bonus = min(1.0, 0.4 * min(action_count, 2) + 0.3 * min(len(all_hits), 3))

            if direct_metrics:
                metric_bonus = min(1.5, 0.8 + 0.3 * len(direct_metrics))
                metric_str = f"verified measurable achievements ({', '.join(direct_metrics[:2])})"
            else:
                metric_bonus = 0.0
                metric_str = "no quantified metrics reported"

            score = base_score + depth_bonus + metric_bonus
            # Realistic cap: never casual 10/10
            score = min(9.0, max(5.5, score))

            actions_found = set(DEMO_ACTION_VERBS.findall(" ".join(m["unit"] for m in matching_units if m["has_action"] and not m["is_intro"])))
            act_summary = ", ".join(list(actions_found)[:3])

            justification = (
                f"[Demo Heuristic - Direct Evidence] Demonstrated active responsibilities ({act_summary}) applying "
                f"{', '.join(sorted(all_hits)[:3])} across {len(matching_units)} resume section(s); {metric_str}. "
                f"Score reflects solid working to advanced proficiency based on job rubric."
            )

        scores.append({
            "competency_id": cid,
            "score": round(score, 1),
            "evidence": evidence,
            "evidence_level": evidence_level,
            "justification": justification
        })

    return {
        "scores": scores,
        "summary": "Demo heuristic scoring; distinguishes direct, partial, and missing evidence with responsibility and verified metrics checks. Not an AI semantic judgement."
    }


# ------------------------------------------------------------------ interviewer
CUES = [
    ("leadership", "Leadership and Mentoring",
     ["mentored", "mentoring", "mentor ", "coached", "led a team", "team lead", "managed a team", "onboarded", "trained junior"],
     'You mentioned "{t}". How did you approach helping them grow, and what would you do differently next time?'),
    ("security", "Security",
     ["security", "vulnerab", "encrypt", "owasp", "authentication", "penetration"],
     'You brought up "{t}". What security risks did you weigh there, and how did you address them?'),
    ("communication", "Stakeholder Communication",
     ["stakeholder", "client", "customer", "product manager", "presented to"],
     'You said "{t}". How did you keep those people informed when things were uncertain or changed?'),
    ("incident", "Incident Response and Reliability",
     ["on-call", "outage", "incident", "postmortem", "rollback"],
     'You mentioned "{t}". Walk me through what happened and what you changed afterwards.'),
]


def _token_window(text: str, idx: int, before: int = 3, after: int = 6) -> str:
    spans = [m.span() for m in re.finditer(r"\S+", text)]
    pos = 0
    for i, (s, e) in enumerate(spans):
        if s <= idx < e or s > idx:
            pos = i
            break
    lo, hi = max(0, pos - before), min(len(spans) - 1, pos + after)
    return text[spans[lo][0]:spans[hi][1]]


def _clean(t: str) -> str:
    return t.strip(" ,;:.-")


def _first_words_substring(text: str, n: int) -> str:
    spans = [m.span() for m in re.finditer(r"\S+", text)]
    if not spans:
        return ""
    return text[spans[0][0]:spans[min(n, len(spans)) - 1][1]]


def _best_sentence(answer: str, kws: List[str]) -> str:
    sents = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if s.strip()] or [answer]
    best = max(sents, key=lambda s: (len(_kw_hits(s, kws)), len(re.findall(r"\d", s))))
    return _first_words_substring(best, 14)


def demo_interviewer(ctx: dict) -> dict:
    answer = ctx["last_answer"]
    allowed = ctx["allowed_decisions"]
    cur = ctx["current_competency"]
    kws = ctx.get("current_keywords", [])
    explored = {x.lower() for x in ctx["already_explored"]}
    unexplored_ids = {c["id"]: c["name"] for c in ctx["unexplored_job_competencies"]}
    low = answer.lower()

    # 1) broad pivot: the answer opened a relevant, not-yet-explored competency
    if "BROAD_PIVOT" in allowed:
        for key, label, cues, tmpl in CUES:
            if key == cur["id"] or label.lower() in explored or unexplored_ids.get(key, "").lower() in explored:
                continue
            hit = next((c for c in cues if c in low), None)
            if hit:
                trig = _token_window(answer, low.index(hit))
                target = key if key in unexplored_ids else label
                return {"trigger_phrase": trig, "decision": "BROAD_PIVOT", "target_competency": target,
                        "reasoning": f"Candidate's answer surfaced '{hit.strip()}', which opens the unplanned competency '{label}'; worth exploring beyond the current technical thread (demo cue-lexicon match).",
                        "question": tmpl.format(t=_clean(truncate_words(trig, 9)))}

    # 2) narrow follow-up if the answer is vague (templates rotate so the same question is never repeated)
    specific = bool(re.search(r"\d", answer)) or bool(_kw_hits(answer, kws))
    if "NARROW_FOLLOW_UP" in allowed and (word_count(answer) < 30 or not specific):
        trig = _first_words_substring(answer, 10) or "(no answer)"
        templates = [
            f'You said "{_clean(truncate_words(trig, 9))}". Can you give one concrete example of what you did and the result?',
            f"Thinking about {cur['name']}, what exactly was your own contribution, and how did you measure the outcome?",
            "Could you walk me through the specific steps you took, and what you would change next time?",
        ]
        fresh = next((q for q in templates if not is_repeat(q, ctx["asked_questions"])), None)
        if fresh:
            return {"trigger_phrase": trig, "decision": "NARROW_FOLLOW_UP", "target_competency": cur["id"],
                    "reasoning": "Answer lacks concrete detail (short or no specifics/metrics), so clarify what the candidate personally did (demo heuristic).",
                    "question": fresh}

    # 3) next competency or conclude
    trig = _best_sentence(answer, kws) or "(no answer)"
    rest = ctx["remaining_planned"]
    if rest:
        nxt = rest[0]
        return {"trigger_phrase": trig, "decision": "NEXT_COMPETENCY", "target_competency": nxt["id"],
                "reasoning": f"Answer on '{cur['name']}' contained enough specifics; moving to planned competency '{nxt['name']}'.",
                "question": nxt["seed_question"]}
    return {"trigger_phrase": trig, "decision": "CONCLUDE",
            "reasoning": "All planned competencies have been covered with adequate evidence."}


# ------------------------------------------------------------------ assessment
def _score_answers(answers: List[str], kws: List[str]):
    text = " ".join(answers)
    wc = word_count(text)
    hits = set(h.lower() for h in _kw_hits(text, kws))
    digits = len(re.findall(r"\b\d+(\.\d+)?\s*(%|x|ms|s|users|requests|people|juniors|engineers)?\b", text))
    verbs = len(re.findall(ACTION_VERBS, text.lower()))
    score = 3 + min(3.0, wc / 40) + min(3.0, len(hits) * 0.8) + min(1.5, digits * 0.5) + min(1.5, verbs * 0.5)
    return round(min(10.0, score), 1), wc, sorted(hits), digits, verbs


def demo_assessment(ctx: dict) -> dict:
    comps_out, strengths, weaknesses, improve = [], [], [], []
    for c in ctx["competencies"]:
        answers = c["answers"]
        score, wc, hits, digits, verbs = _score_answers(answers, c.get("keywords", []))
        sents = [s for a in answers for s in re.split(r"(?<=[.!?])\s+", a.strip()) if len(s) > 8]
        sents.sort(key=lambda s: (-len(_kw_hits(s, c.get("keywords", []))), -len(re.findall(r"\d", s))))
        evidence = [s[:240] for s in sents[:2]]
        comps_out.append({"competency_id": c["id"], "score": score, "evidence": evidence,
                          "rationale": f"{wc} words across {len(answers)} answer(s); {len(hits)} relevant term(s) {hits[:4]}; "
                                       f"{digits} quantified detail(s); {verbs} first-person action statement(s) (demo heuristic)."})
        if score >= 7:
            strengths.append(f"{c['name']}: gave specific, evidence-backed examples.")
        elif score <= 4.5:
            weaknesses.append(f"{c['name']}: answers were thin on concrete detail.")
            top = (c.get("rubric", {}).get("5") or "").strip().rstrip(".")
            improve.append(f"{c['name']}: to show stronger evidence, give a concrete example where you " +
                           (f"demonstrate this: {top[0].lower() + top[1:]}." if top else "explain your role, decisions and measurable results."))
    fb = {
        "summary": "Thank you for interviewing. This feedback is based only on the answers you gave in this session.",
        "strengths": strengths or ["You engaged with every question asked."],
        "weaknesses": weaknesses or ["No major gaps stood out in the topics covered."],
        "improvement_areas": improve or ["Keep adding measurable results to your examples."],
    }
    return {"competencies": comps_out,
            "recruiter_summary": f"Demo-mode heuristic assessment of {len(comps_out)} competencies. Strengths: {len(strengths)}, weaknesses: {len(weaknesses)}. Review the evidence excerpts before deciding.",
            "recommendation_rationale": "Derived from competency scores combined with resume score using the configured weights; final decision rests with the human recruiter.",
            "strengths": strengths, "weaknesses": weaknesses, "candidate_feedback": fb}
