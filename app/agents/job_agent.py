import json
import re

import httpx

from .. import config
from .. import skills as sk
from .base import Agent

SAMPLE_JOBS = json.loads((config.ROOT / "app" / "data" / "jobs.json").read_text())


def _fetch_adzuna(query: str, ctx) -> list[dict]:
    if not (config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY):
        return []
    url = f"https://api.adzuna.com/v1/api/jobs/{config.ADZUNA_COUNTRY}/search/1"
    params = {"app_id": config.ADZUNA_APP_ID, "app_key": config.ADZUNA_APP_KEY, "what": query,
              "results_per_page": 15, "content-type": "application/json"}
    try:
        r = httpx.get(url, params=params, timeout=15)
        r.raise_for_status()
        jobs = []
        for item in r.json().get("results", []):
            desc = item.get("description", "")
            found = sk.extract_skills(f"{item.get('title', '')} {desc}")
            if not found:
                continue
            jobs.append({
                "id": f"az{item.get('id')}", "title": item.get("title", "").strip(),
                "company": (item.get("company") or {}).get("display_name", "Unknown"),
                "location": (item.get("location") or {}).get("display_name", ""),
                "type": item.get("contract_time", "").replace("_", " ").title() or "Full-time",
                "experience": "", "skills_required": found[:6], "nice_to_have": found[6:10],
                "description": re.sub(r"\s+", " ", desc)[:600], "url": item.get("redirect_url"), "source": "Adzuna",
            })
        ctx.log(f"Fetched {len(jobs)} live listings from Adzuna for '{query}'")
        return jobs
    except Exception as exc:
        ctx.log(f"Adzuna unavailable ({type(exc).__name__}); continuing with sample listings", kind="fallback")
        return []


GENERIC = {"engineer", "developer", "software", "associate", "junior", "senior", "the", "and"}


def role_words(target_role: str) -> set[str]:
    words = {w for w in re.findall(r"[a-z+#.]+", (target_role or "").lower()) if len(w) > 1}
    specific = words - GENERIC
    return specific or (words & {"software"}) | {"sde"}


def role_keywords(target_role: str) -> list[str]:
    """Skills that commonly appear in openings matching the target role."""
    rw = role_words(target_role)
    out = []
    for j in SAMPLE_JOBS:
        if rw & set(re.findall(r"[a-z+#.]+", j["title"].lower())):
            out += j["skills_required"]
    return list(dict.fromkeys(out))


def score_job(have: set[str], job: dict, target_role: str) -> dict:
    req = job["skills_required"]
    nice = job.get("nice_to_have", [])
    req_hit = [s for s in req if sk.canonical(s).lower() in have]
    nice_hit = [s for s in nice if sk.canonical(s).lower() in have]
    req_cov = len(req_hit) / len(req) if req else 0
    nice_cov = len(nice_hit) / len(nice) if nice else 0
    title_words = set(re.findall(r"[a-z+#.]+", job["title"].lower()))
    role_fit = bool(role_words(target_role) & title_words)
    role_boost = 0.1 if role_fit else 0
    score = min(1.0, 0.75 * req_cov + 0.25 * nice_cov + role_boost)
    return {"match": round(score * 100), "role_fit": role_fit, "matched": req_hit + nice_hit,
            "missing": [s for s in req if s not in req_hit]}


class JobScoutAgent(Agent):
    name = "jobs"
    label = "Job Scout"
    description = "Discovers openings and ranks them against the student's profile."
    subscribes = ["profile.ready", "target.selected"]

    def handle(self, ctx, event, payload):
        st = ctx.state
        if event == "target.selected":
            job = next((j for j in st["jobs"] if j["id"] == payload["job_id"]), None)
            if not job:
                ctx.log("Selected job not found", kind="error")
                return []
            st["target_job_id"] = job["id"]
            ctx.log(f"Student set target: {job['title']} @ {job['company']}", kind="result")
            return [("target.changed", {"job_id": job["id"]})]

        have = sk.norm_set(st["profile"]["skills"])
        role = st.get("target_role") or "Software Engineer"
        pool = [dict(j, source=j.get("source", "Sample")) for j in SAMPLE_JOBS] + _fetch_adzuna(role, ctx)
        ctx.log(f"Scanning {len(pool)} openings against {len(have)} skills…")

        ranked = []
        for job in pool:
            ranked.append({**job, **score_job(have, job, role)})
        ranked.sort(key=lambda j: j["match"], reverse=True)
        ranked = ranked[:12]

        top = ranked[:5]
        result = self.think(
            ctx,
            "explain why the top openings fit",
            "You are a placement mentor. Be concise and specific.",
            "Student skills: " + ", ".join(st["profile"]["skills"]) + f"\nTarget role: {role}\n"
            + "Jobs:\n" + "\n".join(f"{j['id']}: {j['title']} at {j['company']} needs {', '.join(j['skills_required'])}" for j in top)
            + '\nReturn JSON {"fits": [{"id": str, "reason": "one sentence on fit and the biggest gap"}]}',
        )
        reasons = {f.get("id"): f.get("reason") for f in (result or {}).get("fits", []) if isinstance(f, dict)}
        for j in ranked:
            if j["id"] in reasons:
                j["reason"] = reasons[j["id"]]
            elif "reason" not in j:
                strong = ", ".join(j["matched"][:3]) or "your fundamentals"
                gap = ", ".join(j["missing"][:2])
                j["reason"] = f"Strong on {strong}." + (f" Close the gap on {gap}." if gap else " You meet every core requirement.")

        st["jobs"] = ranked
        ids = {j["id"] for j in ranked}
        if st.get("target_job_id") not in ids:
            # Default target: best-matching opening for the student's stated role, else the overall best match.
            fits = [j for j in ranked if j["role_fit"]]
            st["target_job_id"] = (fits or ranked)[0]["id"]
        target = next(j for j in ranked if j["id"] == st["target_job_id"])
        ctx.log(f"Ranked {len(ranked)} jobs. Best fit: {target['title']} @ {target['company']} ({target['match']}% match)",
                kind="result", data={"top": [(j["title"], j["match"]) for j in top]})
        return [("jobs.ranked", {"job_id": target["id"]})]
