import time

from .base import Agent

WEIGHTS = {"resume": 0.20, "skills": 0.30, "roadmap": 0.25, "interview": 0.25}


def compute(st: dict) -> dict:
    ats = (st.get("ats") or {}).get("score", 0)
    skills = (st.get("gaps") or {}).get("match_pct", 0)
    tasks = [t for w in (st.get("roadmap") or {}).get("plan", []) for t in w["tasks"]]
    done = sum(1 for t in tasks if t["done"])
    roadmap = round(100 * done / len(tasks)) if tasks else 0
    ivs = st.get("interviews", [])
    recent = ivs[-3:]
    interview = round(sum(i["score"] for i in recent) / len(recent)) if recent else 0
    parts = {"resume": ats, "skills": skills, "roadmap": roadmap, "interview": interview}
    readiness = round(sum(parts[k] * w for k, w in WEIGHTS.items()))
    return {"readiness": readiness, "components": parts, "tasks_done": done, "tasks_total": len(tasks),
            "interviews_taken": len(ivs)}


def next_actions(st: dict, p: dict) -> list[str]:
    c = p["components"]
    acts = []
    if c["resume"] < 70 and st.get("ats"):
        acts.append(f"Apply the top resume suggestion: {st['ats']['suggestions'][0]}" if st["ats"]["suggestions"] else "Improve your resume's ATS score.")
    if st.get("roadmap"):
        nxt = next((t for w in st["roadmap"]["plan"] for t in w["tasks"] if not t["done"]), None)
        if nxt:
            acts.append(f"Next roadmap task: {nxt['title']}")
    if p["interviews_taken"] == 0:
        acts.append("Take your first technical mock interview to benchmark yourself.")
    elif c["interview"] < 60:
        weak = st["interviews"][-1].get("weak_topics", [])
        acts.append(f"Retake a mock interview after revising {', '.join(weak[:2]) or 'weak topics'}.")
    if c["skills"] < 60 and st.get("gaps"):
        high = [i["skill"] for i in st["gaps"]["items"] if i["priority"] == "High"][:2]
        if high:
            acts.append(f"Close high-priority gaps: {', '.join(high)}.")
    if p["readiness"] >= 75:
        acts.append("You're placement-ready for this role — start applying to the top matches.")
    return acts[:4]


def level(r: int) -> str:
    return "Placement ready" if r >= 75 else "Almost there" if r >= 55 else "Building up" if r >= 35 else "Getting started"


class ProgressAgent(Agent):
    name = "progress"
    label = "Progress Tracker"
    description = "Computes placement readiness, spots weak areas and triggers re-planning."
    subscribes = ["roadmap.ready", "roadmap.revised", "task.updated", "interview.evaluated"]

    def handle(self, ctx, event, payload):
        st = ctx.state
        prev = (st.get("progress") or {}).get("readiness")
        p = compute(st)
        p["level"] = level(p["readiness"])
        p["next_actions"] = next_actions(st, p)
        p["coach_note"] = (st.get("progress") or {}).get("coach_note", "")

        out = []
        if event == "interview.evaluated":
            weak = payload.get("weak_topics", [])
            result = self.think(
                ctx,
                "write a short coaching note",
                "You are an encouraging but honest placement coach.",
                f"Readiness components (0-100): {p['components']}. Latest {payload.get('mode')} interview score: {payload.get('score')}%. "
                f"Weak topics: {weak}. Target: {(st.get('gaps') or {}).get('job_title')}.\n"
                'Return JSON {"note": "2 sentences of coaching with one concrete next step"}',
            )
            p["coach_note"] = (result or {}).get("note") or (
                f"Interview score {payload.get('score')}%. " + (f"Spend the next few days on {', '.join(weak[:2])} before retaking."
                                                               if weak else "Great consistency — try the HR round next."))
            if weak:
                ctx.log(f"Weak topics detected ({', '.join(weak)}). Asking Roadmap Planner to adapt the plan.", kind="handoff")
                out.append(("weak_topics.detected", {"topics": weak}))

        st["progress"] = p
        st["readiness_history"].append({"t": time.time(), "readiness": p["readiness"], "trigger": event})
        st["readiness_history"] = st["readiness_history"][-60:]
        delta = "" if prev is None else f" ({'+' if p['readiness'] >= prev else ''}{p['readiness'] - prev})"
        ctx.log(f"Readiness {p['readiness']}%{delta} — {p['level']}", kind="result", data=p["components"])
        return out
