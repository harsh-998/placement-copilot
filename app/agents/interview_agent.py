import random
import time

from .. import skills as sk
from .base import Agent

GENERIC_TECH = ["Data Structures", "Algorithms", "OOP", "DBMS", "Operating Systems", "Computer Networks"]


def _fallback_questions(st: dict, mode: str, n: int) -> list[dict]:
    rnd = random.Random(time.time())
    qs = []
    projects = (st.get("profile") or {}).get("projects") or []
    if mode == "hr":
        bank = list(sk.HR_BANK)
        rnd.shuffle(bank)
        qs = [{"topic": t, "question": q, "expected_points": k} for t, q, k in bank]
        if projects:
            qs.insert(1, {"topic": "Ownership", "question": f"In your project '{projects[0].get('name')}', what was the hardest decision you made and why?",
                          "expected_points": ["trade-off", "decision", "result", "learned"]})
        return qs[:n]

    gaps = st.get("gaps") or {}
    topics = [i["skill"] for i in gaps.get("items", [])] + gaps.get("matched", []) + GENERIC_TECH
    seen = set()
    for t in topics:
        bank = sk.TECH_BANK.get(sk.canonical(t))
        if bank and t not in seen:
            seen.add(t)
            topic, q, k = rnd.choice(bank)
            qs.append({"topic": topic, "question": q, "expected_points": k})
        if len(qs) >= n - 1:
            break
    if projects:
        p = projects[0]
        qs.insert(0, {"topic": "Projects", "question": f"Walk me through the architecture of '{p.get('name')}'. What would you change to scale it 10x?",
                      "expected_points": ["architecture", "database", "bottleneck", "cache", "scale"]})
    return qs[:n]


def _fallback_eval(q: dict, answer: str) -> dict:
    a = answer.lower()
    words = len(answer.split())
    pts = q.get("expected_points", [])
    hit = [p for p in pts if p.lower() in a]
    miss = [p for p in pts if p not in hit]
    coverage = len(hit) / len(pts) if pts else 0.5
    score = 0 if words < 3 else round(min(10, 3 * min(1, words / 60) + 7 * coverage))
    fb = []
    if words < 25:
        fb.append("Answer is too short — interviewers expect a structured 1–2 minute explanation.")
    if hit:
        fb.append(f"Good: you covered {', '.join(hit)}.")
    if miss:
        fb.append(f"Strengthen it by discussing {', '.join(miss)}.")
    return {"score": score, "feedback": " ".join(fb) or "Solid answer.", "strengths": hit,
            "improvements": [f"Mention {m}" for m in miss], "ideal_answer": "Key points: " + ", ".join(pts)}


class InterviewAgent(Agent):
    name = "interview"
    label = "Mock Interviewer"
    description = "Runs technical and HR mock interviews tailored to the target job and scores answers."
    subscribes = ["interview.requested", "interview.answered"]

    def handle(self, ctx, event, payload):
        if event == "interview.requested":
            return self._start(ctx, payload)
        return self._evaluate(ctx, payload)

    def _start(self, ctx, payload):
        st = ctx.state
        mode = payload.get("mode", "technical")
        n = int(payload.get("count", 5))
        gaps = st.get("gaps") or {}
        job = gaps.get("job_title", st.get("target_role", "Software Engineer"))
        ctx.log(f"Preparing a {mode} interview ({n} questions) for {job}")

        result = self.think(
            ctx,
            f"generate {mode} interview questions",
            "You are an experienced interviewer at a product company hiring freshers in India.",
            f"Role: {job} at {gaps.get('company', 'a product company')}\nMode: {mode}\n"
            f"Candidate skills: {', '.join((st.get('profile') or {}).get('skills', []))}\n"
            f"Candidate projects: {[p.get('name') for p in (st.get('profile') or {}).get('projects', [])]}\n"
            f"Known skill gaps: {', '.join(i['skill'] for i in gaps.get('items', []))}\n"
            f"Write {n} questions. For technical: mix the candidate's projects, required skills and at least one gap skill. "
            "For hr: behavioural questions using STAR.\n"
            'Return JSON {"questions": [{"topic": "short skill/topic name", "question": str, "expected_points": ["4 key points a strong answer covers"]}]}',
            temperature=0.7,
        )
        qs = [q for q in (result or {}).get("questions", []) if isinstance(q, dict) and q.get("question")][:n]
        if len(qs) < n:
            qs += _fallback_questions(st, mode, n)[: n - len(qs)]
        for i, q in enumerate(qs):
            q["index"] = i
            q.setdefault("topic", "General")
            q.setdefault("expected_points", [])
            q["answer"] = None
            q["evaluation"] = None

        st["active_interview"] = {"id": f"iv{int(time.time())}", "mode": mode, "job_title": job,
                                  "questions": qs, "started_at": time.time(), "finished": False}
        ctx.log(f"Interview ready with {len(qs)} questions", kind="result", data={"topics": [q["topic"] for q in qs]})
        return []

    def _evaluate(self, ctx, payload):
        st = ctx.state
        iv = st.get("active_interview")
        if not iv or iv["finished"]:
            ctx.log("No active interview", kind="error")
            return []
        q = iv["questions"][int(payload["index"])]
        answer = (payload.get("answer") or "").strip()
        q["answer"] = answer
        ctx.log(f"Evaluating answer to Q{q['index'] + 1} ({q['topic']})")

        ev = None
        if len(answer.split()) >= 3:
            result = self.think(
                ctx,
                "score the candidate's answer",
                "You are a fair but demanding interviewer. Score like a real hiring panel.",
                f"Question: {q['question']}\nKey points expected: {q['expected_points']}\nCandidate answer: \"\"\"{answer[:3000]}\"\"\"\n"
                'Return JSON {"score": 0-10 integer, "feedback": "2-3 sentences", "strengths": [str], "improvements": [str], '
                '"ideal_answer": "a concise model answer (4-6 sentences)"}',
            )
            if result and "score" in result:
                try:
                    result["score"] = max(0, min(10, int(float(result["score"]))))
                    ev = {k: result.get(k) for k in ("score", "feedback", "strengths", "improvements", "ideal_answer")}
                except (TypeError, ValueError):
                    ev = None
        q["evaluation"] = ev or _fallback_eval(q, answer)
        ctx.log(f"Q{q['index'] + 1} scored {q['evaluation']['score']}/10", kind="result")

        if all(x["evaluation"] for x in iv["questions"]):
            return self._finish(ctx, iv)
        return []

    def _finish(self, ctx, iv):
        scores = [q["evaluation"]["score"] for q in iv["questions"]]
        avg = sum(scores) / len(scores)
        weak = list(dict.fromkeys(q["topic"] for q in iv["questions"] if q["evaluation"]["score"] < 6))
        strong = list(dict.fromkeys(q["topic"] for q in iv["questions"] if q["evaluation"]["score"] >= 8))
        iv.update(finished=True, finished_at=time.time(), score=round(avg * 10), weak_topics=weak, strong_topics=strong)
        ctx.state["interviews"].append(iv)
        ctx.state["active_interview"] = None
        ctx.log(f"Interview complete: {round(avg * 10)}%. Weak: {', '.join(weak) or 'none'}", kind="result")
        return [("interview.evaluated", {"score": round(avg * 10), "weak_topics": weak, "mode": iv["mode"]})]
