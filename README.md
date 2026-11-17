# Placement Copilot: Agentic AI Career & Placement Assistant

A multi-agent AI system that prepares students for placements. Six specialised agents work together through an event-driven **orchestrator** to:

1. analyse the resume and score its ATS readiness
2. find and rank relevant job openings
3. find skill gaps by comparing the resume with job descriptions
4. write a personalised week-by-week learning roadmap
5. run AI mock interviews (technical and HR) and score each answer
6. track placement readiness and **re-plan automatically** when the student is weak in an area

Stack: **Python, FastAPI, SQLite, vanilla JS** (no build step). LLM: **any OpenAI-compatible API** (Groq, Gemini, OpenAI, Ollama). With no key, every agent switches to built-in logic, so the app still runs end to end.

---

## Run it

**Windows:** double-click `start.bat`
**macOS / Linux:** `./start.sh`

Or manually:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
python run.py
```

The browser opens at http://localhost:8000. On startup the terminal prints whether the LLM key works.

### Turn on AI reasoning (recommended, free)

1. Get a free key from https://console.groq.com/keys (or https://aistudio.google.com/apikey for Gemini).
2. Put it in `.env` as `LLM_API_KEY=...` (`.env.example` has the Gemini, OpenAI and Ollama settings).
3. Restart `python run.py` and check for `LLM: OK` in the terminal.

Optional: add Adzuna keys (https://developer.adzuna.com) to get live job listings alongside the built-in sample listings.

---

## Architecture

```
                       ┌──────────────────────────────────────────┐
  Browser UI  ──REST──►│ FastAPI                                  │
  (polls state         │   │                                      │
   + agent trace)      │   ▼                                      │
                       │ ORCHESTRATOR (event bus)                 │
                       │  • routes each event to subscribed agents│
                       │  • persists shared state after each step │
                       │  • logs a trace (shown live in the UI)   │
                       │  • step limit prevents infinite loops    │
                       │   │                                      │
                       │   ├─► Resume Analyst      📄              │
                       │   ├─► Job Scout           🔎              │
                       │   ├─► Skill Gap Analyzer  🧩              │
                       │   ├─► Roadmap Planner     🗺️              │
                       │   ├─► Mock Interviewer    🎤              │
                       │   └─► Progress Tracker    📈              │
                       │            │                             │
                       │      LLM (OpenAI-compatible) + fallbacks │
                       │      SQLite: student state + event log   │
                       └──────────────────────────────────────────┘
```

**Agents never call each other directly.** Each agent subscribes to events, reads and updates the **shared student state**, and emits new events. The orchestrator routes them. This is a publish/subscribe (blackboard) design, which keeps agents loosely coupled: you can add an agent without touching the others.

### Workflows

| Trigger | Chain |
|---|---|
| Resume uploaded | `resume.uploaded` → Resume Analyst → `profile.ready` → Job Scout → `jobs.ranked` → Skill Gap Analyzer → `gaps.identified` → Roadmap Planner → `roadmap.ready` → Progress Tracker |
| Student picks a different target job | `target.selected` → Job Scout → `target.changed` → Skill Gap → Roadmap → Progress |
| **Feedback loop** | `interview.answered` → Mock Interviewer → `interview.evaluated` → Progress Tracker → `weak_topics.detected` → Roadmap Planner (adds revision tasks) → `roadmap.revised` → Progress Tracker |
| Roadmap task ticked | `task.toggled` → Roadmap Planner → `task.updated` → Progress Tracker |

### Agents

| Agent | Responsibility | LLM role | Deterministic fallback |
|---|---|---|---|
| Resume Analyst | Structured profile (skills, projects, experience, education), ATS score and suggestions | Extraction + recruiter-style review | 75-skill taxonomy, section/impact/keyword scoring |
| Job Scout | Collects openings (sample + Adzuna), ranks by weighted skill coverage, picks the best-fit target | Explains why each top job fits | Rule-based fit explanation |
| Skill Gap Analyzer | Required vs nice-to-have gaps, market demand across top jobs, effort estimates | Prioritises gaps and explains their impact | Priority by requirement type, effort table |
| Roadmap Planner | Week-by-week plan (learn / practice / build / interview) with resources; adapts to feedback | Writes the plan | Template planner |
| Mock Interviewer | Questions tailored to the target job, the student's projects and gaps; scores answers | Writes questions, scores answers, gives a model answer | Curated question bank + keyword-coverage scoring |
| Progress Tracker | Readiness = 20% ATS + 30% skill match + 25% roadmap + 25% interviews; next best actions; triggers re-planning | Coaching note | Rule-based note |

### Project layout

```
app/
  main.py            REST API
  orchestrator.py    event bus, routing, persistence, tracing
  llm.py             OpenAI-compatible client (JSON mode, retries, fallback signal)
  db.py              SQLite: students (JSON state) + events (trace)
  skills.py          skill taxonomy, learning resources, question bank
  agents/            one file per agent (base.py = shared Agent class)
  data/jobs.json     sample job openings
static/              UI (index.html, app.js, style.css)
sample_resume.txt    demo resume
```

### API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/students` | create a student workspace |
| POST | `/api/students/{id}/resume` | upload PDF/DOCX/TXT or text → starts the pipeline |
| GET | `/api/students/{id}` | full shared state |
| GET | `/api/students/{id}/events?after=` | agent trace |
| POST | `/api/students/{id}/target` | set target job |
| POST | `/api/students/{id}/roadmap` | regenerate roadmap (weeks) |
| POST | `/api/students/{id}/tasks/{task_id}` | tick or untick a task |
| POST | `/api/students/{id}/interview/start` | start a technical or HR interview |
| POST | `/api/students/{id}/interview/answer` | submit an answer |
| GET | `/api/config` | agents, routes, LLM status |

Interactive docs: http://localhost:8000/docs

---

## Demo script (about 5 minutes)

1. **Problem (30s).** Placement prep is fragmented: resume tools, job boards, courses and mock interviews don't talk to each other. This system connects them with agents that share context.
2. **Upload (1 min).** Enter a name, set the target role to *Full Stack Developer*, click **Use sample resume**, then **Run copilot**. Point at the activity panel: each agent lights up as the orchestrator routes events to it.
3. **Walk the results (1.5 min).** Show the Resume tab (ATS breakdown + suggestions), Jobs (ranked, with ✓/✗ skills), Skill Gap (priorities + market demand) and Roadmap (weekly tasks with resources).
4. **Change target (30s).** On Jobs, click **Set as target** on another job. The gap analysis and roadmap re-run on their own (workflow 2).
5. **Feedback loop (1.5 min).** Start a 3-question technical interview. Answer one well and one badly. When it finishes, the Progress Tracker finds weak topics and hands them to the Roadmap Planner, which adds revision tasks (marked "added by Interview feedback"). Show this in the trace and on the Roadmap.
6. **Architecture (30s).** Open **How it works** and explain the event routing, shared state and graceful fallback.

### Likely questions

- **Why is this "agentic" and not just API calls?** Agents are autonomous units with their own responsibility and memory (the shared state). They react to events and trigger each other through the orchestrator without a human in between, and the interview → progress → roadmap loop adapts the plan by itself.
- **Why event-driven instead of one big prompt?** Each agent can be tested on its own, retried and swapped independently. The trace makes every decision auditable, and the step limit makes runaway loops impossible.
- **What if the LLM fails?** Each agent catches the failure, logs a fallback event and uses its deterministic logic, so the workflow still completes.
- **How is the job match computed?** 75% required-skill coverage + 25% nice-to-have coverage, plus a 10% boost when the job title matches the student's target role.
- **Next steps:** live job APIs at scale, an LLM-based router for free-form chat ("what should I do today?"), voice mock interviews, a placement-cell admin dashboard, vector search over job descriptions.
