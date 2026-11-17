from collections import Counter

from .. import skills as sk
from .base import Agent

# Rough weeks needed to become interview-ready in a skill, for the offline fallback.
EFFORT = {"Language": 3, "Frontend": 2, "Backend": 2, "Database": 1, "DevOps": 1, "Cloud": 2, "AI/ML": 3,
          "Data": 1, "CS Fundamentals": 3, "Mobile": 3, "Testing": 1, "Process": 1, "Design": 1, "Soft Skill": 1}


class SkillGapAgent(Agent):
    name = "gap"
    label = "Skill Gap Analyzer"
    description = "Compares the resume with target job descriptions and prioritises missing skills."
    subscribes = ["jobs.ranked", "target.changed"]

    def handle(self, ctx, event, payload):
        st = ctx.state
        have = sk.norm_set(st["profile"]["skills"])
        job = next(j for j in st["jobs"] if j["id"] == st["target_job_id"])
        req, nice = job["skills_required"], job.get("nice_to_have", [])

        matched = [s for s in req + nice if sk.canonical(s).lower() in have]
        miss_req = [s for s in req if sk.canonical(s).lower() not in have]
        miss_nice = [s for s in nice if sk.canonical(s).lower() not in have]
        match_pct = round(100 * (len(req) - len(miss_req)) / len(req)) if req else 100
        ctx.log(f"Target {job['title']}: {len(req) - len(miss_req)}/{len(req)} core skills present; "
                f"missing {', '.join(miss_req) or 'none'}")

        # Market view: which missing skills keep showing up across the top openings?
        market = Counter()
        for j in st["jobs"][:8]:
            for s in j["skills_required"] + j.get("nice_to_have", []):
                if sk.canonical(s).lower() not in have:
                    market[s] += 1
        market_gaps = [{"skill": s, "count": c} for s, c in market.most_common(6)]

        items = [{"skill": s, "priority": "High", "kind": "required"} for s in miss_req] + \
                [{"skill": s, "priority": "Medium", "kind": "nice"} for s in miss_nice]
        for it in items:
            it["est_weeks"] = EFFORT.get(sk.category(it["skill"]), 2)
            it["why"] = (f"Listed as a core requirement for {job['title']}." if it["kind"] == "required"
                         else f"Nice-to-have that strengthens your {job['title']} application.")

        summary = (f"You match {match_pct}% of the core requirements for {job['title']} at {job['company']}. "
                   + (f"Focus first on {', '.join(miss_req[:3])}." if miss_req else "Polish the nice-to-haves and interview skills."))

        result = self.think(
            ctx,
            "prioritise gaps and explain impact",
            "You are a technical hiring manager mentoring a final-year student.",
            f"Job: {job['title']} at {job['company']}\nDescription: {job['description']}\n"
            f"Required: {', '.join(req)}\nNice to have: {', '.join(nice)}\n"
            f"Student skills: {', '.join(st['profile']['skills'])}\n"
            f"Student projects: {[p.get('name') for p in st['profile'].get('projects', [])]}\n"
            f"Missing: {', '.join(miss_req + miss_nice) or 'none'}\n"
            'Return JSON {"summary": "2-3 sentences", "gaps": [{"skill": str, "priority": "High|Medium|Low", '
            '"why": "one sentence tied to this job", "est_weeks": int}], '
            '"transferable": ["skills or projects the student can leverage"]}',
        )
        if result:
            by_skill = {sk.canonical(g.get("skill", "")).lower(): g for g in result.get("gaps", []) if isinstance(g, dict)}
            for it in items:
                g = by_skill.get(sk.canonical(it["skill"]).lower())
                if g:
                    it["priority"] = g.get("priority", it["priority"]) if g.get("priority") in ("High", "Medium", "Low") else it["priority"]
                    it["why"] = g.get("why") or it["why"]
                    try:
                        it["est_weeks"] = max(1, min(8, int(g.get("est_weeks", it["est_weeks"]))))
                    except (TypeError, ValueError):
                        pass
            summary = result.get("summary") or summary
            transferable = [t for t in result.get("transferable", []) if isinstance(t, str)]
        else:
            transferable = matched[:5]

        order = {"High": 0, "Medium": 1, "Low": 2}
        items.sort(key=lambda i: order.get(i["priority"], 3))
        st["gaps"] = {
            "job_id": job["id"], "job_title": job["title"], "company": job["company"],
            "match_pct": match_pct, "matched": matched, "items": items,
            "market_gaps": market_gaps, "transferable": transferable, "summary": summary,
        }
        ctx.log(f"Identified {len(items)} gaps ({sum(1 for i in items if i['priority'] == 'High')} high priority)",
                kind="result", data={"gaps": [i["skill"] for i in items]})
        return [("gaps.identified", {})]
