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
    r"established|cut|spearheaded|drove|scaled|"
    r"eliminated|avoided|separated|separates|validated|mapped|dispatched|isolated|prevented|"
    r"resolved|decoupled|absorbed|preserved|structured|handled|provided|caught|adjusted|"
    r"injected|guarded|identified|revealed|inspected|diagnosed|extracted|applied|introduced|"
    r"enforced|adding|rewriting|replacing|structuring|"
    r"separating|validating|dispatching|isolating|mapping|handling)\b",
    re.I
)

DEMO_INTRO_PASSIVE = re.compile(
    r"\b(learned|intern|college project|simple|basic|seeking|learning|student|"
    r"familiar with|elementary|coursework|academic project|minor project)\b",
    re.I
)

DEMO_MEASURABLE_METRIC = re.compile(
    r"(?:"
    r"\b\d+(?:\.\d+)?\s*%(?:\s*(?:reduction|increase|improvement|coverage|faster|latency|stability)\b)?|"
    r"\b\d[\d,]*(?:[kmKM])?\+?\s*(?:requests|req|qps|rps|users|concurrent|records|events|messages|tps)\s*(?:per\s*(?:sec|second|day|month)|/s)?\b|"
    r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds|seconds)\s*(?:latency|response|faster)?\b|"
    r"\b(?:team\s*of|led|managed|mentored)\s*(\d{1,2})\s*(?:engineers|developers|people|juniors|members)\b|"
    r"\b\d{1,3}\+?\s*(?:rest\s+api\s+|api\s+)?(?:endpoints|microservices|services|apis|pipelines|modules|clusters)\b"
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
REASONING_TERMS = re.compile(
    r"\b(because|due to|in order to|so that|so they could|so it cannot|trade-off|tradeoff|"
    r"trade-offs|tradeoffs|trade off|chose|chosen|decided|decision|weighed|why we|the reason|"
    r"rationale|prevent|prevented|instead of|approach|architecture|pattern|strategy|solution|"
    r"resolved by|root cause|diagnosed|troubleshot|reproducing|investigation|investigated|"
    r"ensuring|ensure|eliminated|avoided|mitigated|safely permit|permit retries|separation of concerns)\b",
    re.I
)

VAGUE_TERMS = re.compile(
    r"\b(a bit|somewhat|not much|basic knowledge|briefly|superficial|read about|heard of|just started|not really)\b",
    re.I
)

DISMISSIVE_TERMS = re.compile(
    r"^(no|nope|not really|don't know|dont know|not sure|never used|haven't used|havent used|no idea|n/a)\b",
    re.I
)

GENERIC_WORDS = {
    # Common English words, prepositions, conjunctions, pronouns
    "with", "that", "this", "from", "some", "such", "have", "well", "give", "good",
    "about", "above", "across", "after", "again", "against", "almost", "along", "also",
    "always", "among", "another", "around", "because", "been", "before", "being", "below",
    "between", "both", "came", "come", "could", "does", "done", "down", "during", "each",
    "even", "every", "find", "first", "further", "great", "group", "had", "has",
    "having", "help", "here", "high", "into", "just", "keep", "know", "large",
    "last", "like", "long", "look", "made", "make", "many", "more", "most", "much",
    "must", "never", "next", "often", "once", "only", "other", "others", "over", "part",
    "place", "real", "same", "seem", "should", "show", "small", "still", "take",
    "than", "their", "them", "then", "there", "these", "they", "thing", "things",
    "think", "those", "through", "time", "under", "until", "upon", "used", "uses",
    "very", "want", "went", "were", "what", "when", "where", "which", "while", "will",
    "without", "would", "year", "years",
    # Generic workspace, actions, nouns, and rubric vocabulary
    "clean", "writes", "writing", "wrote", "written", "build", "builds", "building", "built",
    "work", "works", "worked", "working", "service", "services", "module", "modules",
    "system", "systems", "design", "designs", "designed", "code", "codes", "coding",
    "basic", "script", "scripts", "experience", "experienced", "level", "levels",
    "standard", "standards", "practices", "practice", "practical",
    "concept", "concepts", "knowledge", "skills", "skill", "ability", "able",
    "demonstrate", "demonstrates", "demonstrated", "demonstrating",
    "deliver", "delivers", "delivered", "delivering",
    "create", "creates", "created", "creating",
    "handle", "handles", "handled", "handling",
    "support", "supports", "supported", "supporting",
    "team", "teams", "teammate", "teammates", "member", "members", "peer", "peers",
    "project", "projects", "task", "tasks", "solution", "solutions", "issue", "issues",
    "application", "applications", "environment", "environments",
    "quality", "efficient", "efficiency", "maintainable", "maintain", "maintaining",
    "consistent", "consistently", "reliable", "reliability",
    "scalable", "scalability", "simple", "complex", "complexity",
    "various", "different", "multiple", "general", "overall", "process", "processes",
    "method", "methods", "approach", "approaches", "role", "roles",
    "ensure", "ensures", "ensured", "ensuring",
    "grow", "grows", "grown", "growing", "growth",
    "manage", "manages", "managed", "managing", "management",
    "guide", "guides", "guided", "guiding", "guidance",
    "better", "best", "higher", "highest", "lower", "lowest",
    "easy", "hard", "faster", "fast", "slow", "slower",
    "structure", "structures", "structured",
    "production", "explain", "explains", "explained", "explaining",
    "trade", "offs", "inside", "outside", "existing", "contribute", "contributes", "contributed",
    "consideration", "considerations", "understand", "understands", "understood", "understanding",
    "follow", "follows", "followed", "following",
    "model", "models", "modeled", "modeling",
    "data", "outcome", "outcomes", "result", "results", "value", "values",
    "people", "person", "daily", "weekly", "monthly", "regular", "regularly",
    "start", "starts", "started", "starting", "stop", "stops", "stopped",
    "open", "close", "read", "reads", "reading", "write", "note", "notes",
    "step", "steps", "way", "ways", "idea", "ideas", "change", "changes", "changed",
    "need", "needs", "needed", "needing", "user", "users", "helps", "helping",
    "desk", "habit", "habits", "kitchen", "dinner", "eating", "food", "running",
    "family", "wooden", "furniture", "varnish", "legs", "wobble", "pantry",
    "baking", "bread", "sourdough", "outdoors", "marathon", "marathons", "weekends", "chores",
}

COMPETENCY_DOMAIN_TAXONOMY = {
    "databases": [
        "query execution plan", "query execution plans", "execution plan", "execution plans",
        "query plan", "query plans", "table scan", "table scans", "full table scan",
        "full table scans", "composite index", "composite indexes", "b-tree", "btree",
        "indexing", "indexes", "subquery", "subqueries", "inner join", "inner joins",
        "outer join", "outer joins", "nested loop", "nested loops", "hash join", "hash joins",
        "lock contention", "deadlock", "deadlocks", "concurrent update", "concurrent updates",
        "write lock", "write locks", "row-level locking", "table lock", "table locks",
        "acid", "isolation level", "isolation levels", "read committed", "repeatable read",
        "serializable", "table partitioning", "partitioning", "sharding", "replication",
        "read replica", "read replicas", "write-ahead log", "wal", "connection pool",
        "connection pooling", "foreign key", "foreign keys", "primary key", "primary keys",
        "normalization", "denormalization", "migration", "migrations", "schema design",
        "slow query", "slow queries", "query optimization", "storage engine",
        "thread pool starvation", "unindexed", "eager loading", "lazy loading",
        "postgresql", "postgres", "mysql", "redis", "mongodb", "sqlite", "dynamodb", "cassandra"
    ],
    "api_design": [
        "http transport", "transport representation", "transport representations",
        "data transfer object", "data transfer objects", "dto", "dtos",
        "request payload", "request payloads", "payload validation", "schema validation",
        "service handler", "service handlers", "error envelope", "error envelopes",
        "error response", "error responses", "standardized error", "machine-readable",
        "idempotency", "idempotency key", "idempotency keys", "client retry", "client retries",
        "cursor pagination", "offset pagination", "pagination", "api versioning", "versioning",
        "backward compatibility", "breaking change", "breaking changes", "contract", "contracts",
        "openapi", "swagger", "graphql", "status code", "status codes", "rate limiting",
        "throttling", "endpoint", "endpoints", "crud", "restful", "rest api", "middleware",
        "serialization", "deserialization", "domain entities", "separation of concerns"
    ],
    "system_design": [
        "event-driven", "message broker", "message brokers", "decouple", "decoupling",
        "producers", "consumers", "producer", "consumer", "ingestion pipeline", "ingestion",
        "upstream spikes", "worker pool", "worker pools", "sustainable rate", "partition key",
        "partition keys", "ordering guarantee", "ordering guarantees", "dead-letter queue",
        "dead letter queue", "dead-letter queues", "dlq", "poisonous payload", "poisonous payloads",
        "asynchronous inspection", "circuit breaker", "circuit breakers", "backpressure",
        "load balancer", "load balancers", "load balancing", "reverse proxy", "eventual consistency",
        "strong consistency", "cap theorem", "fault tolerance", "high availability",
        "horizontal scaling", "cache invalidation", "distributed system", "distributed systems",
        "microservices", "microservice", "failover", "redundancy", "throughput", "latency"
    ],
    "python": [
        "generator expression", "generator expressions", "generators", "generator",
        "itertools", "functools", "streaming data", "context manager", "context managers",
        "resource cleanup", "type annotation", "type annotations", "type hints",
        "static verification", "coroutine", "coroutines", "asyncio", "decorator", "decorators",
        "comprehension", "comprehensions", "dataclass", "dataclasses", "dunder", "magic methods",
        "metaclass", "gil", "multiprocessing", "threading", "cpython", "intermediate lists",
        "garbage collection", "fastapi", "flask", "django", "pytest", "pydantic", "pandas",
        "separation of concerns"
    ],
    "testing": [
        "contract verification", "breaking schema", "deterministic fixtures", "fixtures",
        "ephemeral database", "ephemeral instances", "isolate state", "flaky assertions",
        "flaky tests", "flaky test", "race condition", "race conditions", "concurrent suite",
        "test suite", "test suites", "mocking", "unit test", "unit tests", "integration test",
        "integration tests", "regression test", "regression testing", "code coverage",
        "assertions", "tdd", "e2e", "test runner", "ci pipeline"
    ],
    "cloud_devops": [
        "multi-stage compilation", "multi-stage build", "container images", "container image",
        "surface area", "development dependencies", "horizontal pod autoscaling", "autoscaling",
        "replica counts", "cpu saturation", "memory saturation", "blue-green deployment",
        "blue-green", "canary deployment", "downtime", "production rollouts", "rollout",
        "rollback", "kubernetes", "docker", "terraform", "infrastructure as code",
        "ci/cd pipeline", "helm charts", "service mesh"
    ],
    "problem_solving": [
        "memory profiling", "retain cycle", "background worker", "garbage collection",
        "decommissioned session", "heap allocations", "thread dump", "thread dumps",
        "memory leak", "memory leaks", "subscription handler", "root cause", "root causes",
        "bottleneck", "bottlenecks", "flamegraph", "cpu spike", "reproduce issue",
        "stack trace", "investigation"
    ],
    "security": [
        "input sanitization", "parameterized query", "parameterized queries", "injection vectors",
        "sql injection", "sensitive credentials", "cryptographic secrets", "runtime environment",
        "source control", "rate limiting", "brute-force", "credential stuffing",
        "authentication", "authorization", "rbac", "oauth2", "jwt", "tls encryption",
        "vulnerability", "vulnerabilities", "owasp", "penetration testing"
    ],
    "leadership": [
        "mentoring", "mentored", "coaching", "coached", "pairing", "pair programming",
        "code reviews", "pull request feedback", "onboarding", "delegating", "scoping tasks",
        "helping grow", "technical guidance", "career development", "knowledge sharing"
    ],
    "communication": [
        "stakeholder communication", "decision document", "architecture decision record",
        "adr", "downtime window", "timeline", "rollback plan", "trade-off explanation",
        "non-technical audiences", "presenting proposals", "consensus building"
    ],
}


def _get_competency_domains(comp: dict) -> List[str]:
    cid = str(comp.get("id", "")).lower()
    cname = str(comp.get("name", "")).lower()
    kws = [str(k).lower() for k in comp.get("keywords") or []]

    domains = []
    if any(k in cid or k in cname for k in ["database", "sql", "data_storage"]) or any("sql" in k or "database" in k or "query" in k for k in kws):
        domains.append("databases")
    if any(k in cid or k in cname for k in ["api", "rest"]) or any("api" in k or "rest" in k or "endpoint" in k for k in kws):
        domains.append("api_design")
    if any(k in cid or k in cname for k in ["system", "distributed", "architecture"]) or any("system" in k or "microservice" in k or "kafka" in k for k in kws):
        domains.append("system_design")
    if any(k in cid or k in cname for k in ["python"]) or any("python" in k or "fastapi" in k or "django" in k for k in kws):
        domains.append("python")
    if any(k in cid or k in cname for k in ["test", "qa", "quality"]) or any("test" in k or "pytest" in k for k in kws):
        domains.append("testing")
    if any(k in cid or k in cname for k in ["cloud", "devops", "infra"]) or any("docker" in k or "kubernetes" in k or "aws" in k for k in kws):
        domains.append("cloud_devops")
    if any(k in cid or k in cname for k in ["problem", "debug", "troubleshoot"]) or any("debug" in k or "profil" in k for k in kws):
        domains.append("problem_solving")
    if any(k in cid or k in cname for k in ["security", "auth"]) or any("security" in k or "owasp" in k for k in kws):
        domains.append("security")
    if any(k in cid or k in cname for k in ["lead", "mentor"]) or any("mentor" in k or "lead" in k for k in kws):
        domains.append("leadership")
    if any(k in cid or k in cname for k in ["comm", "stakeholder"]) or any("stakeholder" in k for k in kws):
        domains.append("communication")
    return domains


def _has_meaningful_explanation(text: str) -> bool:
    reasoning_hits = set(m.group(0).lower() for m in REASONING_TERMS.finditer(text))
    if not reasoning_hits:
        return False

    has_clause = bool(re.search(
        r"\b(because|due to|in order to|so that|so they could|so it cannot|trade-off|tradeoff|"
        r"chose|chosen|decided|instead of|root cause|diagnosed|resolved by|prevent|prevented|"
        r"mitigated|ensuring|ensure|avoided|eliminated|safely permit|rationale|why we|"
        r"separation of concerns)\b",
        text,
        re.I
    ))
    return has_clause


def _score_answers(answers: List[str], comp: dict):
    """Score interview answers against competency expectations using relevance, actions, and reasoning.

    Tiers:
    - Missing (0.0 - 1.5): Empty, dismissive, or irrelevant (no competency overlap)
    - Partial (2.5 - 4.5): Vague, introductory/coursework, or passive tool mentions without concrete actions
    - Strong (6.5 - 8.0): Competency relevance + concrete actions + technical explanation/reasoning (no metrics required)
    - Excellent (8.5 - 10.0): Strong evidence + architectural trade-offs, multi-service scope, and/or verified metrics
    """
    text = " ".join(answers).strip()
    wc = word_count(text)
    if not text:
        return 0.0, 0, [], 0, 0

    if DISMISSIVE_TERMS.search(text) and wc < 15:
        return 0.0, wc, [], 0, 0

    name = comp.get("name", "")
    kws = list(comp.get("keywords") or [])

    # Domain terms: non-generic keywords + competency name + domain taxonomy
    # Generic English words from descriptions/rubrics must NOT establish competency relevance
    domain_terms = [k for k in kws if k.lower() not in GENERIC_WORDS]
    if name and name.lower() not in GENERIC_WORDS and name.lower() not in [k.lower() for k in domain_terms]:
        domain_terms.append(name)

    domains = _get_competency_domains(comp)
    for d in domains:
        for term in COMPETENCY_DOMAIN_TAXONOMY.get(d, []):
            if term.lower() not in [t.lower() for t in domain_terms]:
                domain_terms.append(term)

    raw_hits = _kw_hits(text, domain_terms)
    hits = set(h.lower() for h in raw_hits if h.lower() not in GENERIC_WORDS)

    # Extract evidence signals
    actions = set(m.group(0).lower() for m in DEMO_ACTION_VERBS.finditer(text))
    action_count = len(actions)
    metrics = _extract_genuine_metrics(text)
    has_metrics = len(metrics) > 0

    # If answers have zero relevance to the competency, score as Missing (0.0)
    # Generic words or irrelevant answers with action verbs must never receive relevance/strong scores
    if not hits:
        return 0.0, wc, [], len(metrics), action_count

    reasoning_hits = set(m.group(0).lower() for m in REASONING_TERMS.finditer(text))
    has_reasoning = len(reasoning_hits) > 0
    is_intro = bool(DEMO_INTRO_PASSIVE.search(text)) or bool(VAGUE_TERMS.search(text))
    has_meaningful_exp = _has_meaningful_explanation(text)

    # Distinguish evidence tiers:
    if action_count == 0 or is_intro or not has_meaningful_exp:
        # Partial evidence: mentions tools/keywords but lacks concrete actions, is introductory/vague,
        # or lists buzzwords/metrics without meaningful explanation
        if is_intro:
            score = 2.5 + min(1.0, 0.3 * len(hits))
            score = min(3.5, score)
        elif not has_meaningful_exp and has_metrics:
            # Buzzwords and metrics without meaningful explanation: must not receive strong or excellent scores
            score = 3.5 + min(1.0, 0.3 * min(len(hits), 3))
            score = min(4.5, score)
        else:
            score = 3.5 + min(1.0, 0.3 * (len(hits) - 1))
            score = min(4.5, score)
    else:
        # Direct evidence: has concrete actions, relevance, and meaningful technical explanation
        base_score = 6.5
        depth_bonus = min(1.0, 0.3 * min(action_count, 3) + 0.2 * min(len(hits), 3))
        reasoning_bonus = 0.5 if has_reasoning else 0.0

        # Metrics are optional: strong score is achieved without metrics
        metric_bonus = min(1.5, 0.8 + 0.3 * len(metrics)) if has_metrics else 0.0

        score = base_score + depth_bonus + reasoning_bonus + metric_bonus
        # Cap excellent evidence realistically
        score = min(9.5, max(6.5, score))

    return round(score, 1), wc, sorted(hits), len(metrics), action_count


def _clean_no_digits(text: str) -> str:
    cleaned = re.sub(r"\d+", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,;.-")


PRACTICE_SUGGESTIONS = {
    "databases": (
        "Practice walking through a database performance tuning scenario: explain how you analyze query execution plans, "
        "select composite indexing strategies, and resolve transaction isolation or lock contention issues."
    ),
    "api_design": (
        "Practice detailing end-to-end REST API architecture: explain contract design with schema validation, "
        "idempotency keys for safe client retries, cursor pagination, and backward-compatible versioning."
    ),
    "system_design": (
        "Practice diagramming distributed architecture trade-offs: explain how you evaluate message broker decoupling versus synchronous calls, "
        "partitioning strategies, cache invalidation policies, and failure isolation patterns."
    ),
    "python": (
        "Practice discussing production-grade Python patterns: walk through how you structure layered backend services, "
        "manage asynchronous concurrency with asyncio, use type annotations for static verification, and build automated pytest suites."
    ),
    "testing": (
        "Practice explaining comprehensive test strategies: discuss deterministic fixture management, contract verification, "
        "and designing integration tests that reproduce race conditions or prevent CI regressions."
    ),
    "cloud_devops": (
        "Practice detailing infrastructure automation and deployment pipelines: discuss container multi-stage builds, "
        "horizontal autoscaling triggers, blue-green deployment rollouts, and automated rollback health checks."
    ),
    "problem_solving": (
        "Practice structured root-cause debugging narratives: walk through how you isolate bottlenecks using profiling tools, "
        "inspect stack traces or thread dumps, formulate hypotheses, and implement regression-proof fixes."
    ),
    "security": (
        "Practice explaining defense-in-depth security measures: discuss input sanitization, OAuth and JWT token flows, "
        "role-based access control, cryptographic secret management, and mitigating common OWASP security vulnerabilities."
    ),
    "leadership": (
        "Practice structuring leadership and mentorship examples using the STAR method: explain how you scope tasks for juniors, "
        "conduct constructive code reviews, and guide teammates through technical ownership."
    ),
    "communication": (
        "Practice articulating complex technical trade-offs to cross-functional stakeholders: focus on authoring architecture decision records, "
        "negotiating downtime windows, and aligning engineering timelines with business priorities."
    ),
}


def demo_assessment(ctx: dict) -> dict:
    from app.textutil import contains_quote
    comps_out, recruiter_strengths, recruiter_weaknesses = [], [], []
    cand_strengths, cand_weaknesses, cand_improvements = [], [], []
    scores_by_cid = {}

    planned = ctx.get("planned_competencies") or [c["id"] for c in ctx["competencies"]]
    assessed_ids = [c["id"] for c in ctx["competencies"] if c.get("answers")]
    coverage = len(set(planned) & set(assessed_ids)) / len(set(planned)) if planned else 1.0
    min_cov = ctx.get("min_coverage", 0.75)
    is_provisional = coverage < min_cov
    missing_cids = [cid for cid in planned if cid not in assessed_ids]
    missing_names = [c.get("name", cid) for cid in missing_cids for c in [next((x for x in ctx["competencies"] if x["id"] == cid), {"name": cid})]]

    for c in ctx["competencies"]:
        cid = c["id"]
        cname = c["name"]
        answers = c["answers"]
        score, wc, hits, digits, verbs = _score_answers(answers, c)
        scores_by_cid[cid] = score

        all_ans_text = " ".join(answers)
        sents = [s for a in answers for s in re.split(r"(?<=[.!?])\s+", a.strip()) if len(s) > 8]
        domain_kws = c.get("keywords", []) or [c.get("name", "")]
        sents.sort(key=lambda s: (
            -len(_kw_hits(s, domain_kws)),
            -bool(DEMO_ACTION_VERBS.search(s)),
            -len(s)
        ))

        # Verbatim evidence extraction satisfying semantic check
        if score <= 2.0 and not hits:
            evidence = []
        else:
            evidence = [s[:240] for s in sents if contains_quote(all_ans_text, s[:240])][:2]
            if score > 2.0 and not evidence and sents:
                evidence = [sents[0][:200]]

        if score == 0.0:
            evidence_desc = "missing evidence"
        elif score <= 4.5:
            evidence_desc = "partial evidence"
        elif score >= 8.5:
            evidence_desc = "excellent evidence"
        else:
            evidence_desc = "strong evidence"

        rationale = (
            f"[{evidence_desc.title()}] Evaluated across {len(answers)} answer(s); "
            f"identified {len(hits)} relevant domain term(s), {verbs} concrete action(s), "
            f"and {digits} verified metric(s) (demo heuristic)."
        )

        comps_out.append({"competency_id": cid, "score": score, "evidence": evidence, "rationale": rationale})

        # Actions found in text
        actions_found = sorted(list(set(m.group(0).lower() for m in DEMO_ACTION_VERBS.finditer(all_ans_text))))
        act_summary = ", ".join(actions_found[:2]) if actions_found else "applied techniques"
        hits_summary = ", ".join(hits[:3]) if hits else "core concepts"

        # Determine competency domain for practice suggestion
        domains = _get_competency_domains(c)
        dom = domains[0] if domains else "general"
        practice_suggestion = PRACTICE_SUGGESTIONS.get(dom, (
            "Prepare concrete production-scale examples that clearly explain your personal role, "
            "the architectural choices evaluated, and the measurable results achieved."
        ))

        if score >= 6.5:
            recruiter_strengths.append(f"{cname}: Demonstrated verified technical competence with concrete evidence in {hits_summary}.")
            if digits > 0:
                cand_strengths.append(
                    f"{cname}: Demonstrated strong technical capability by actively implementing {hits_summary} ({act_summary}), backed by verified outcomes and clear technical reasoning."
                )
            else:
                cand_strengths.append(
                    f"{cname}: Demonstrated solid practical proficiency in {hits_summary}, clearly explaining your technical approach ({act_summary}) and architectural considerations."
                )
        else:
            recruiter_weaknesses.append(f"{cname}: Technical evidence was partial or lacking concrete implementation details.")
            is_intro = bool(DEMO_INTRO_PASSIVE.search(all_ans_text)) or bool(VAGUE_TERMS.search(all_ans_text))
            has_meaningful_exp = _has_meaningful_explanation(all_ans_text)
            if score == 0.0 or not hits:
                cand_weaknesses.append(
                    f"{cname}: Responses did not provide concrete technical examples or implementation details demonstrating hands-on experience in this competency."
                )
            elif is_intro:
                cand_weaknesses.append(
                    f"{cname}: Discussion was centered on introductory or coursework projects rather than production-scale responsibilities, architectural trade-offs, or measurable outcomes."
                )
            elif not has_meaningful_exp:
                cand_weaknesses.append(
                    f"{cname}: Key technical tools were mentioned, but the explanation lacked context on the underlying problem, how implementation decisions were made, or why specific trade-offs were chosen."
                )
            else:
                cand_weaknesses.append(
                    f"{cname}: Responses were high-level and lacked depth regarding specific actions you personally took and concrete technical mechanisms used."
                )
            cand_improvements.append(f"{cname}: {practice_suggestion}")

    # Fallbacks ensuring non-empty lists without generic boilerplate
    comp_names = [c["name"] for c in ctx["competencies"]]
    strong_cnames = [c["name"] for c in ctx["competencies"] if scores_by_cid.get(c["id"], 0) >= 6.5]
    weak_cnames = [c["name"] for c in ctx["competencies"] if scores_by_cid.get(c["id"], 0) <= 4.5]

    if not cand_strengths:
        cand_strengths.append("Demonstrated willingness to engage with technical questions and communicate your background.")
    if not cand_weaknesses:
        cand_weaknesses.append("No critical competency gaps were identified in the topics evaluated during this session.")
    if not cand_improvements:
        cand_improvements.append("Continue deepening technical depth by quantifying production impact and leading complex architectural trade-offs.")

    # Candidate summary - NO numeric scores, personalized, evidence-based
    if strong_cnames and weak_cnames:
        cand_summary = (
            f"This feedback reflects your responses across {', '.join(comp_names)} in this interview session. "
            f"You demonstrated strong competence in {', '.join(strong_cnames)}, providing concrete technical context and clear implementation details. "
            f"To strengthen your technical presentation, focus on deepening examples in {', '.join(weak_cnames)} with production trade-offs and problem-solving depth."
        )
    elif strong_cnames:
        cand_summary = (
            f"This feedback reflects your responses across {', '.join(comp_names)} in this interview session. "
            f"You demonstrated strong, evidence-backed proficiency across all evaluated topics, clearly explaining your architectural decisions and practical contributions."
        )
    else:
        cand_summary = (
            f"This feedback reflects your responses across {', '.join(comp_names)} in this interview session. "
            f"While you engaged with each topic, your answers remained largely introductory or high-level. "
            f"Focus on preparing detailed production-level project walkthroughs highlighting your personal technical contributions and problem-solving mechanisms."
        )
    if is_provisional:
        cand_summary += " Note: This session covered a subset of planned topics; feedback is specific to the competencies evaluated."

    fb = {
        "summary": _clean_no_digits(cand_summary),
        "strengths": [_clean_no_digits(s) for s in cand_strengths if _clean_no_digits(s)],
        "weaknesses": [_clean_no_digits(w) for w in cand_weaknesses if _clean_no_digits(w)],
        "improvement_areas": [_clean_no_digits(i) for i in cand_improvements if _clean_no_digits(i)],
    }

    # Recruiter summary - factual, complete vs provisional distinction
    if is_provisional:
        comp_status = (
            f"PROVISIONAL ASSESSMENT: Candidate was evaluated on {len(assessed_ids)} of {len(planned)} planned competencies "
            f"({int(coverage * 100)}% coverage, minimum {int(min_cov * 100)}% required). "
            f"Unassessed planned competencies: {', '.join(missing_names) if missing_names else 'None'}. "
            f"Unassessed areas reflect interview time or progression constraints and must not be treated as evidence of poor candidate ability."
        )
    else:
        comp_status = f"COMPLETE ASSESSMENT: Evaluated across all {len(assessed_ids)} planned competencies ({', '.join(comp_names)})."

    if strong_cnames:
        strong_stmt = f"Candidate demonstrated verified direct evidence in {', '.join(strong_cnames)}."
    else:
        strong_stmt = "Candidate did not demonstrate strong direct evidence in the assessed competencies."

    if weak_cnames:
        weak_stmt = f"Evidence was partial or missing in {', '.join(weak_cnames)}."
    else:
        weak_stmt = "No major technical deficiencies were identified in the assessed competencies."

    if is_provisional:
        next_step = "Human recruiter review is required before an advancement decision can be made."
    elif strong_cnames and not weak_cnames:
        next_step = "Technical evidence supports advancement to the next evaluation stage based on job rubric requirements."
    else:
        next_step = "Review evidence excerpts to determine role fit."

    recruiter_summary = f"{comp_status} {strong_stmt} {weak_stmt} {next_step}"

    # Recommendation rationale
    w_res = ctx.get("weights", {}).get("resume", 0.4)
    w_int = ctx.get("weights", {}).get("interview", 0.6)
    adv_min = ctx.get("thresholds", {}).get("advance_min", 70.0)
    rev_min = ctx.get("thresholds", {}).get("review_min", 50.0)
    res_score = ctx.get("resume_summary", {}).get("resume_score_0_100", 0.0) or 0.0
    tw = sum(c.get("weight", 1.0) for c in ctx["competencies"])
    int_score = sum(c.get("weight", 1.0) * scores_by_cid.get(c["id"], 0.0) for c in ctx["competencies"]) / tw * 10 if tw > 0 else 0.0
    comb_score = round(w_res * res_score + w_int * int_score, 1)

    if is_provisional:
        rec_rationale = (
            f"BORDERLINE RECRUITER REVIEW (PROVISIONAL): Interview coverage ({int(coverage * 100)}%) is below the {int(min_cov * 100)}% requirement, "
            f"so candidate cannot receive an automated advance recommendation. "
            f"While performance on assessed topics ({', '.join(strong_cnames) if strong_cnames else 'None'}) scored {int_score:.1f}/100, "
            f"unassessed competencies ({', '.join(missing_names) if missing_names else 'None'}) require recruiter review or a supplemental session."
        )
    elif comb_score >= adv_min:
        rec_rationale = (
            f"RECOMMEND ADVANCE: Combined score of {comb_score:.1f} (Resume {res_score:.1f} @ {int(w_res*100)}%, Interview {int_score:.1f} @ {int(w_int*100)}%) "
            f"meets the advancement threshold of {adv_min:.1f}. Candidate demonstrated verified competence in {', '.join(strong_cnames)}."
        )
    elif comb_score >= rev_min:
        rec_rationale = (
            f"BORDERLINE RECRUITER REVIEW: Combined score of {comb_score:.1f} (Resume {res_score:.1f} @ {int(w_res*100)}%, Interview {int_score:.1f} @ {int(w_int*100)}%) "
            f"falls in the review range ({rev_min:.1f} - {adv_min:.1f}). Candidate demonstrated competence in {', '.join(strong_cnames) if strong_cnames else 'select areas'}, "
            f"with gaps in {', '.join(weak_cnames) if weak_cnames else 'other areas'} requiring recruiter judgment."
        )
    else:
        rec_rationale = (
            f"NOT RECOMMENDED: Combined score of {comb_score:.1f} is below the review threshold of {rev_min:.1f}. "
            f"Candidate provided insufficient evidence across key competencies ({', '.join(weak_cnames) if weak_cnames else 'evaluated topics'})."
        )

    return {
        "competencies": comps_out,
        "recruiter_summary": recruiter_summary,
        "recommendation_rationale": rec_rationale,
        "strengths": recruiter_strengths or ["Candidate demonstrated willingness to engage with technical questions."],
        "weaknesses": recruiter_weaknesses or ["No major competency gaps stood out in the evaluated topics."],
        "candidate_feedback": fb,
    }
