"""Generates ALL synthetic demo data: sample_jd.json, mock_calendar.json, 6 fictional resumes (3 DOCX, 3 PDF),
and a placeholder avatar. Everything is fictional. Run:  python data/generate_demo_data.py"""
import json
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "sample"
(OUT / "resumes").mkdir(parents=True, exist_ok=True)


def C(id, name, desc, weight, kws, q, r1, r3, r5):
    return {"id": id, "name": name, "description": desc, "weight": weight, "keywords": kws, "questions": [q],
            "rubric": {"1": r1, "3": r3, "5": r5}}


COMPETENCIES = [
    C("python", "Python Programming", "Writes clean, idiomatic, maintainable Python.", 1.5,
      ["python", "pandas", "asyncio", "fastapi", "flask", "django", "pytest"],
      "Tell me about a Python codebase you are proud of. What made it maintainable?",
      "Only basic scripts; no evidence of structure.", "Builds working services/modules in Python with some structure.",
      "Designs well-structured, tested, idiomatic Python systems and explains trade-offs."),
    C("api_design", "REST API Design", "Designs consistent, versioned, well-documented APIs.", 1.2,
      ["rest", "api", "endpoint", "openapi", "swagger", "graphql", "pagination", "versioning"],
      "Walk me through how you designed an API that other teams relied on.",
      "Has consumed APIs only.", "Has built CRUD APIs with basic validation.",
      "Designs versioned APIs with contracts, error handling, pagination and backward compatibility."),
    C("databases", "Databases and SQL", "Models data, writes efficient queries, understands indexing and transactions.", 1.2,
      ["sql", "postgresql", "mysql", "index", "query", "schema", "transaction", "redis", "mongodb", "orm"],
      "Describe a time you had to fix a slow database query or redesign a schema.",
      "Basic CRUD queries only.", "Designs schemas and writes joins/indexes for real workloads.",
      "Diagnoses performance with query plans, designs for scale and consistency, explains trade-offs."),
    C("system_design", "System Design", "Designs scalable, reliable systems and reasons about trade-offs.", 1.2,
      ["architecture", "microservices", "scalab", "queue", "kafka", "rabbitmq", "cache", "load balanc", "distributed", "design"],
      "Tell me about a system you designed or significantly re-architected. What trade-offs did you make?",
      "Works inside existing designs.", "Contributes to designs of services with some scale considerations.",
      "Leads designs, quantifies load, explains failure modes and trade-offs."),
    C("testing", "Testing and Quality", "Writes automated tests and builds quality into the process.", 1.0,
      ["test", "pytest", "unit test", "integration test", "ci", "coverage", "tdd", "mock"],
      "How do you decide what to test, and can you give an example where tests caught a serious bug?",
      "Tests manually.", "Writes unit tests for own code.",
      "Builds layered test strategy, automates in CI, uses tests to enable safe refactoring."),
    C("cloud_devops", "Cloud and DevOps", "Deploys and operates services on cloud infrastructure.", 1.0,
      ["aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ci/cd", "deploy", "github actions", "jenkins", "monitoring"],
      "Describe how your last service went from a pull request to production.",
      "Has not deployed services.", "Containerises and deploys with a pipeline.",
      "Owns infra-as-code, observability and safe rollouts."),
    C("problem_solving", "Problem Solving", "Breaks down ambiguous problems and debugs systematically.", 1.2,
      ["debug", "root cause", "optimi", "profil", "algorithm", "reduced", "improved", "bottleneck", "investigat"],
      "Tell me about the hardest bug or performance problem you solved. How did you approach it?",
      "Relies on trial and error.", "Debugs methodically and fixes root causes in familiar areas.",
      "Forms hypotheses, measures, finds root causes in unfamiliar systems and prevents recurrence."),
    C("communication", "Communication and Collaboration", "Explains technical ideas clearly and works well with others.", 0.8,
      ["stakeholder", "documentation", "presented", "collaborat", "cross-functional", "code review", "wrote"],
      "Tell me about a time you had to explain a technical decision to a non-technical stakeholder.",
      "Limited evidence of collaboration.", "Communicates clearly within the team.",
      "Adapts to audiences, documents decisions, builds alignment across teams."),
    C("leadership", "Leadership and Mentoring", "Mentors others and drives technical direction.", 0.6,
      ["mentor", "led a team", "team lead", "coached", "onboard", "managed", "ownership"],
      "Tell me about a time you helped another engineer grow or led a piece of work.",
      "No leadership evidence.", "Has mentored or led small pieces of work.",
      "Grows others, sets direction, takes accountability for team outcomes."),
    C("security", "Security Awareness", "Applies secure-coding and data-protection practices.", 0.8,
      ["security", "oauth", "jwt", "authentication", "authorization", "encrypt", "owasp", "vulnerab", "sanitiz"],
      "How do you approach security when building a new feature that handles user data?",
      "Unaware of common risks.", "Applies authentication and input validation.",
      "Threat-models features, applies defence in depth, handles secrets and audits dependencies."),
]
JD = {"title": "Backend Python Engineer",
      "description": "Build and operate Python/FastAPI services for a SaaS product. 2-6 years of experience, strong fundamentals in APIs, databases, testing and cloud deployment.",
      "competencies": COMPETENCIES}
(OUT / "sample_jd.json").write_text(json.dumps(JD, indent=2))

# ---- mock calendar: next 5 weekdays, 6 x 45-min slots/day, two rooms ----
slots, n = [], 1
day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
days = 0
while days < 5:
    if day.weekday() < 5:
        for room in ("AI-Room-1", "AI-Room-2"):
            for h in (10, 11, 14, 15):
                st = day.replace(hour=h)
                slots.append({"slot_id": f"S{n:03d}", "resource": room, "start": st.isoformat(timespec="minutes"),
                              "end": (st + timedelta(minutes=45)).isoformat(timespec="minutes")})
                n += 1
        days += 1
    day += timedelta(days=1)
(OUT / "mock_calendar.json").write_text(json.dumps({"slots": slots}, indent=2))

# ---- synthetic resumes ----
R = {
 "Aarav_Mehta": ("docx", "Aarav Mehta", "aarav.mehta@example.com", "+91 98765 43210",
  "Backend engineer with 5 years of experience building Python services.",
  ["Senior Backend Engineer, Finlytics (2021 - 2026)",
   "Designed and built 12 REST API endpoints with FastAPI and OpenAPI documentation; introduced cursor pagination and versioning.",
   "Reduced PostgreSQL query latency by 60% by adding composite indexes and rewriting slow SQL queries.",
   "Re-architected a monolith into microservices using Kafka queues, handling 3,000 requests per second with Redis cache.",
   "Wrote pytest unit tests and integration tests reaching 92% coverage; enforced in CI with GitHub Actions.",
   "Deployed services on AWS using Docker, Kubernetes and Terraform with Prometheus monitoring.",
   "Debugged a memory leak through profiling and root cause analysis, improving stability by 40%.",
   "Implemented OAuth2 and JWT authentication and fixed OWASP vulnerabilities found in a security audit."],
  "B.Tech Computer Science, National Institute of Technology"),
 "Priya_Nair": ("pdf", "Priya Nair", "priya.nair@example.com", "+91 91234 56780",
  "Software engineer with 4 years of experience in Python backend development and team collaboration.",
  ["Backend Developer, ShopSphere (2022 - 2026)",
   "Built REST API endpoints in Flask and FastAPI used by the mobile app; documented with Swagger.",
   "Designed PostgreSQL schemas and wrote SQL queries with indexes for the orders module.",
   "Mentored two junior developers, ran code review sessions and onboarded new hires.",
   "Wrote pytest unit tests for core payment logic; set up a basic CI pipeline.",
   "Containerised services with Docker and deployed to AWS.",
   "Collaborated with product managers and presented release plans to stakeholders."],
  "B.E. Information Technology, State Engineering College"),
 "Rohan_Gupta": ("docx", "Rohan Gupta", "rohan.gupta@example.com", "+91 99887 76655",
  "Developer with 3 years of experience in Python scripting and Django web applications.",
  ["Software Developer, WebCraft (2023 - 2026)",
   "Developed Django applications with MySQL and built several API endpoints.",
   "Wrote Python scripts to automate reporting using pandas.",
   "Fixed production bugs and improved page load time by optimizing queries.",
   "Participated in code review and documentation."],
  "B.Sc Computer Science, City University"),
 "Sneha_Kulkarni": ("pdf", "Sneha Kulkarni", "sneha.kulkarni@example.com", "+91 90000 11122",
  "Frontend developer with 2 years of experience, learning backend development.",
  ["Frontend Developer, PixelWorks (2024 - 2026)",
   "Built React and TypeScript user interfaces consumed REST APIs.",
   "Wrote basic Python scripts for data cleaning.",
   "Collaborated with designers and presented demos to clients."],
  "B.Tech Electronics, Institute of Technology"),
 "Karan_Shah": ("docx", "Karan Shah", "karan.shah@example.com", "+91 95555 44433",
  "Recent graduate seeking a backend role. Completed projects in Python.",
  ["Intern, StartupLab (2025 - 2026)",
   "Built a small Flask API for a college project using SQLite.",
   "Learned Git and wrote simple unit tests with pytest."],
  "B.Tech Computer Science, Regional Engineering College"),
 "Meera_Iyer": ("pdf", "Meera Iyer", "meera.iyer@example.com", "+91 94444 33221",
  "Platform engineer with 6 years of experience in Python, cloud infrastructure and reliability.",
  ["Platform Engineer, CloudNine (2020 - 2026)",
   "Built Python automation and FastAPI internal tools; designed REST APIs with versioning and pagination.",
   "Designed distributed architecture with Kafka and RabbitMQ queues, scalable to 10,000 requests per second.",
   "Led a team of 4 engineers and mentored juniors; owned on-call rotation and wrote postmortems after incidents.",
   "Deployed infrastructure on AWS and GCP using Terraform, Kubernetes, Docker, Jenkins CI/CD and Grafana monitoring.",
   "Improved database performance with PostgreSQL index tuning and Redis caching, reducing latency by 45%.",
   "Wrote pytest suites with 85% coverage; investigated incidents to find root cause."],
  "M.Tech Software Systems, Indian Institute of Technology"),
}


def make_docx(path, name, email, phone, summary, bullets, edu):
    import docx
    d = docx.Document()
    d.add_heading(name, 0)
    d.add_paragraph(f"{email} | {phone}")
    d.add_paragraph(summary)
    d.add_heading("Experience", 1)
    d.add_paragraph(bullets[0])
    for b in bullets[1:]:
        d.add_paragraph(b, style="List Bullet")
    d.add_heading("Education", 1)
    d.add_paragraph(edu)
    d.save(path)


def make_pdf(path, name, email, phone, summary, bullets, edu):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    st = getSampleStyleSheet()
    flow = [Paragraph(name, st["Title"]), Paragraph(f"{email} | {phone}", st["Normal"]), Spacer(1, 8),
            Paragraph(summary, st["Normal"]), Spacer(1, 8), Paragraph("Experience", st["Heading2"]),
            Paragraph(bullets[0], st["Normal"])]
    flow += [Paragraph("- " + b, st["Normal"]) for b in bullets[1:]]
    flow += [Paragraph("Education", st["Heading2"]), Paragraph(edu, st["Normal"])]
    SimpleDocTemplate(str(path), pagesize=A4).build(flow)


for key, (kind, *rest) in R.items():
    p = OUT / "resumes" / f"{key}.{kind}"
    (make_docx if kind == "docx" else make_pdf)(p, *rest)

# placeholder avatar (NOT a real face; the demo identity adapter does not analyse it)
try:
    import cv2, numpy as np
    img = np.full((240, 240, 3), 220, np.uint8)
    cv2.circle(img, (120, 100), 50, (150, 150, 150), -1)
    cv2.ellipse(img, (120, 220), (80, 60), 0, 180, 360, (150, 150, 150), -1)
    cv2.imwrite(str(OUT / "photos" / "placeholder_avatar.png"), img)
except ImportError:
    pass

# scripted candidate answers keyed by competency id (used by scripts/run_demo_cli.py, tests and docs/DEMO.md).
# The databases answer deliberately mentions mentoring juniors so the Interviewer can BROAD_PIVOT to leadership.
(OUT / "demo_answers.json").write_text(json.dumps({
    "python": "I maintain a FastAPI service with about 40 endpoints. I structured it into routers and services, wrote pytest tests with 90 percent coverage, and used type hints so new teammates could navigate it quickly.",
    "api_design": "I designed a versioned REST API that three other teams consumed. I used OpenAPI contracts, cursor pagination and consistent error responses, and I kept v1 working for six months while teams migrated.",
    "databases": "I fixed a slow PostgreSQL query by reading the query plan, adding a composite index and rewriting a join, which cut latency by 60 percent. I also mentored two juniors through that investigation so they could do it themselves next time.",
    "system_design": "I designed a Kafka based pipeline handling 3000 requests per second. I chose queues over direct calls to absorb spikes and added a Redis cache; the trade-off was eventual consistency, which we documented for the clients.",
    "testing": "Tests caught a race condition in payments. I wrote an integration test reproducing it, fixed the lock ordering, and added it to CI with GitHub Actions so it cannot regress.",
    "cloud_devops": "We deployed through GitHub Actions to AWS using Docker. I added health checks and automatic rollback, which reduced failed releases by half.",
    "problem_solving": "I profiled a slow endpoint, found an N+1 query as the root cause, fixed it with eager loading and added a regression test. Latency dropped from 900 ms to 120 ms.",
    "communication": "I explained a database migration risk to our product manager using a simple timeline and a rollback plan, wrote a one page decision document, and the stakeholders approved the downtime window.",
    "leadership": "I helped them grow by pairing twice a week, giving small scoped tickets, and reviewing their pull requests with explanations. One of them now owns a service and I coached her through her first on-call.",
    "security": "I added OAuth2 with JWT, validated and sanitised every input, stored secrets in a vault and ran OWASP dependency checks in CI; a pen test later found no critical issues.",
    "_followup": "Specifically, I wrote the migration script myself, tested it against a copy of production data, measured the result at 40 percent faster, and presented the outcome to the team.",
    "_generic": "I took ownership of the task, planned it with the team, implemented the solution myself, and measured the result at 30 percent improvement.",
}, indent=2))
print("generated demo data in", OUT)
