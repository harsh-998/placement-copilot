import time

from .. import skills as sk
from .base import Agent

PROJECT_IDEAS = {
    "Frontend": "a responsive dashboard with search, filters and charts",
    "Backend": "a REST API with auth, pagination and validation",
    "Database": "a normalised schema with seed data and 10 analytical queries",
    "DevOps": "a containerised app with a CI pipeline that runs tests on every push",
    "Cloud": "a deployed app on a free cloud tier with logs and monitoring",
    "AI/ML": "an end-to-end model notebook plus a small inference API",
    "Data": "a cleaned dataset and a dashboard answering 5 business questions",
    "CS Fundamentals": "a set of 25 solved problems with written complexity analysis",
    "Language": "a CLI tool that solves a real problem you have",
    "Mobile": "a two-screen app consuming a public API",
    "Testing": "a test suite with >70% coverage for one of your projects",
}


def _focus_skills(gaps: dict, limit: int) -> list[str]:
    skills = [i["skill"] for i in gaps["items"]]
    for m in gaps.get("market_gaps", []):
        if m["skill"] not in skills:
            skills.append(m["skill"])
    if len(skills) < 2:
        skills += [s for s in ["Data Structures", "System Design", "Algorithms"] if s not in skills]
    return skills[:limit]


def _fallback_weeks(focus: list[str], weeks: int, job_title: str) -> list[dict]:
    plan = []
    per_week = max(1, -(-len(focus) // weeks))  # ceil
    for w in range(weeks):
        chunk = focus[w * per_week:(w + 1) * per_week] or focus[-1:]
        main = chunk[0]
        tasks = []
        for s in chunk:
            tasks.append({"title": f"Learn {s} fundamentals", "type": "learn", "skill": s, "hours": 6})
            tasks.append({"title": f"Solve 5 hands-on exercises in {s}", "type": "practice", "skill": s, "hours": 4})
        idea = PROJECT_IDEAS.get(sk.category(main), "a small project using this week's skills")
        tasks.append({"title": f"Build: {idea} using {' + '.join(chunk)}", "type": "build", "skill": main, "hours": 8})
        tasks.append({"title": "Solve 6 DSA problems (2 easy, 3 medium, 1 hard)", "type": "practice", "skill": "Data Structures", "hours": 4})
        if w == weeks - 1:
            tasks.append({"title": f"Full mock interview for {job_title} and update resume with new projects", "type": "interview", "skill": "", "hours": 2})
        plan.append({"week": w + 1, "theme": f"{' & '.join(chunk)}", "goal": f"Be able to explain and use {', '.join(chunk)} in an interview.", "tasks": tasks})
    return plan


class RoadmapAgent(Agent):
    name = "roadmap"
    label = "Roadmap Planner"
    description = "Turns skill gaps into a week-by-week learning plan and adapts it to feedback."
    subscribes = ["gaps.identified", "roadmap.regenerate", "weak_topics.detected", "task.toggled"]

    def handle(self, ctx, event, payload):
        st = ctx.state
        if event == "task.toggled":
            return self._toggle(ctx, payload)
        if event == "weak_topics.detected":
            return self._revise(ctx, payload)

        weeks = int(payload.get("weeks") or (st.get("roadmap") or {}).get("weeks") or 4)
        gaps = st["gaps"]
        focus = _focus_skills(gaps, limit=weeks * 2)
        ctx.log(f"Planning a {weeks}-week roadmap around: {', '.join(focus)}")
        plan = None

        result = self.think(
            ctx,
            f"design a {weeks}-week learning roadmap",
            "You are a placement coach who writes realistic study plans for students with ~20 hours/week.",
            f"Target job: {gaps['job_title']} at {gaps['company']}\n"
            f"Student already knows: {', '.join(st['profile']['skills'])}\n"
            f"Skills to close, in priority order: {', '.join(focus)}\n"
            f"Weeks: {weeks}\n"
            'Return JSON {"weeks": [{"week": int, "theme": str, "goal": str, "tasks": [{"title": str, '
            '"type": "learn|practice|build|interview", "skill": str, "hours": int}]}]}. '
            "4-6 tasks per week. Each week must include one concrete build task and DSA practice. "
            "The final week must include a mock interview.",
            max_tokens=8000,
        )
        if result and isinstance(result.get("weeks"), list) and result["weeks"]:
            plan = []
            for i, w in enumerate(result["weeks"][:weeks]):
                tasks = [t for t in w.get("tasks", []) if isinstance(t, dict) and t.get("title")]
                if tasks:
                    plan.append({"week": i + 1, "theme": w.get("theme", f"Week {i + 1}"), "goal": w.get("goal", ""), "tasks": tasks})
        fallback = _fallback_weeks(focus, weeks, gaps["job_title"])
        if not plan:
            plan = fallback
        elif len(plan) < weeks:  # model returned fewer weeks than asked: pad with planned weeks
            plan += [dict(w, week=i + 1) for i, w in enumerate(fallback) if i >= len(plan)]

        for w in plan:
            for j, t in enumerate(w["tasks"]):
                t["id"] = f"w{w['week']}t{j + 1}"
                t["done"] = False
                t.setdefault("type", "learn")
                try:
                    t["hours"] = int(t.get("hours", 4))
                except (TypeError, ValueError):
                    t["hours"] = 4
                skill = t.get("skill") or ""
                t["resources"] = sk.resources_for(skill) if skill and t["type"] in ("learn", "practice") else []

        st["roadmap"] = {"weeks": weeks, "job_title": gaps["job_title"], "focus": focus, "plan": plan,
                         "created_at": time.time(), "revisions": []}
        total = sum(len(w["tasks"]) for w in plan)
        ctx.log(f"Roadmap ready: {weeks} weeks, {total} tasks, ~{sum(t['hours'] for w in plan for t in w['tasks'])} hours",
                kind="result")
        return [("roadmap.ready", {})]

    def _toggle(self, ctx, payload):
        for w in ctx.state["roadmap"]["plan"]:
            for t in w["tasks"]:
                if t["id"] == payload["task_id"]:
                    t["done"] = bool(payload["done"])
                    ctx.log(f"Task {'completed' if t['done'] else 'reopened'}: {t['title']}")
                    return [("task.updated", {})]
        return []

    def _revise(self, ctx, payload):
        rm = ctx.state.get("roadmap")
        if not rm:
            return []
        topics = payload["topics"]
        week = next((w for w in rm["plan"] if not all(t["done"] for t in w["tasks"])), rm["plan"][-1])
        added = []
        for topic in topics:
            tid = f"w{week['week']}r{len(week['tasks']) + 1}"
            week["tasks"].append({
                "id": tid, "title": f"Revisit {topic}: re-study weak areas from your mock interview and answer 3 practice questions aloud",
                "type": "practice", "skill": topic, "hours": 3, "done": False,
                "resources": sk.resources_for(topic), "added_by": "Interview feedback",
            })
            added.append(topic)
        rm["revisions"].append({"at": time.time(), "week": week["week"], "topics": added})
        ctx.log(f"Adapted roadmap: added reinforcement for {', '.join(added)} to week {week['week']}", kind="result")
        return [("roadmap.revised", {})]
