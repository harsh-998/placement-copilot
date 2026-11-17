import re

from .. import skills as sk
from .base import Agent

SECTION_HEADS = {
    "education": r"education|academic",
    "experience": r"experience|internship|employment|work history",
    "projects": r"projects?",
    "skills": r"skills|technical skills|technologies",
    "achievements": r"achievements|awards|accomplishments|certifications?|extracurricular",
}
ACTION_VERBS = ["built", "developed", "designed", "implemented", "led", "created", "optimized", "improved", "deployed",
                "trained", "automated", "reduced", "increased", "launched", "architected", "engineered", "integrated", "managed"]


def _heuristic_profile(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    lower = text.lower()
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    phone = re.search(r"(\+?\d[\d\s-]{8,}\d)", text)
    links = re.findall(r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com)/[\w\-/]+", text, re.I)
    cgpa = re.search(r"(?:cgpa|gpa)[^\d]{0,10}(\d{1,2}(?:\.\d{1,2})?)", lower)

    # Collect lines under a "Projects" heading as project titles.
    projects, in_proj = [], False
    for l in lines:
        if re.fullmatch(r"(?i)(academic |personal |key )?projects?:?", l):
            in_proj = True
            continue
        if in_proj and re.fullmatch(r"(?i)(" + "|".join(SECTION_HEADS.values()) + r").{0,15}", l) and len(l) < 35:
            break
        if in_proj and not l.startswith(("-", "•", "*")) and 3 < len(l) < 90:
            name = re.split(r"\s[|–-]\s|:", l)[0].strip()
            projects.append({"name": name, "tech": sk.extract_skills(l), "summary": ""})
    return {
        "name": lines[0] if lines and len(lines[0]) < 50 else "Student",
        "email": email.group(0) if email else "",
        "phone": phone.group(0).strip() if phone else "",
        "links": list(dict.fromkeys(links)),
        "cgpa": float(cgpa.group(1)) if cgpa else None,
        "skills": sk.extract_skills(text),
        "projects": projects[:6],
        "experience": [],
        "education": [],
        "summary": "",
        "strengths": [],
    }


def _heuristic_ats(text: str, profile: dict, target_role: str) -> dict:
    from .job_agent import role_keywords
    lower = text.lower()
    words = len(text.split())
    sections = {k: bool(re.search(r"(?im)^\s*(" + v + r")\b", text)) for k, v in SECTION_HEADS.items()}
    bullets = [l for l in text.splitlines() if l.strip().startswith(("-", "•", "*", "–"))]
    quantified = [b for b in bullets if re.search(r"\d+%|\d+\+|\d{2,}|\bx\d", b)]
    verbs = sum(1 for v in ACTION_VERBS if re.search(rf"\b{v}\b", lower))

    have = sk.norm_set(profile["skills"])
    kws = role_keywords(target_role)
    kw_hit = [k for k in kws if sk.canonical(k).lower() in have]
    kw_miss = [k for k in kws if k not in kw_hit]

    contact = (4 if profile["email"] else 0) + (2 if profile["phone"] else 0) + min(4, 2 * len(profile["links"]))
    structure = round(20 * sum(sections.values()) / len(sections))
    skills_pts = min(15, len(profile["skills"]))
    impact = min(18, len(quantified) * 3) + min(7, verbs)
    role_pts = round(20 * len(kw_hit) / len(kws)) if kws else 10
    length = 10 if 300 <= words <= 800 else 6 if 180 <= words <= 1100 else 2
    breakdown = {"Contact & links": contact, "Section structure": structure, "Skills listed": skills_pts,
                 "Impact & action verbs": min(25, impact), f"Keywords for {target_role}": role_pts, "Length": length}
    score = min(100, sum(breakdown.values()))

    tips = []
    if kw_miss:
        tips.append(f"Recruiters searching for {target_role} roles look for: {', '.join(kw_miss[:5])}. Add any you genuinely know.")
    if not profile["links"]:
        tips.append("Add your GitHub and LinkedIn URLs in the header.")
    for sec, ok in sections.items():
        if not ok and sec != "achievements":
            tips.append(f"Add a clearly labelled '{sec.title()}' section so ATS parsers can find it.")
    if len(quantified) < 3:
        tips.append(f"Quantify more bullets (users, %, latency, accuracy) — only {len(quantified)} have numbers.")
    if verbs < 5:
        tips.append("Start bullets with strong action verbs (Built, Optimized, Deployed…).")
    if words > 900:
        tips.append("Trim to one page for a fresher resume (~400–700 words).")
    if len(profile["skills"]) < 8:
        tips.append("List more relevant tools and frameworks in a dedicated Skills section.")
    return {"score": score, "breakdown": breakdown, "suggestions": tips}


class ResumeAgent(Agent):
    name = "resume"
    label = "Resume Analyst"
    description = "Parses the resume into a structured profile and scores ATS readiness."
    subscribes = ["resume.uploaded"]

    def handle(self, ctx, event, payload):
        text = payload["text"]
        ctx.state["resume_text"] = text
        ctx.log(f"Received resume ({len(text.split())} words). Extracting structure…")

        profile = _heuristic_profile(text)
        ats = _heuristic_ats(text, profile, ctx.state.get("target_role") or "Software Engineer")
        ctx.log(f"Detected {len(profile['skills'])} skills via taxonomy; heuristic ATS score {ats['score']}/100",
                data={"skills": profile["skills"]})

        result = self.think(
            ctx,
            "structured profile + ATS review",
            "You are a senior technical recruiter and resume parser for Indian campus placements.",
            f"""Target role: {ctx.state.get('target_role') or 'Software Engineer'}
Resume:
\"\"\"{text[:7000]}\"\"\"

Return JSON with keys:
name, summary (2 sentences), skills (list of technical skills, canonical names),
projects (list of {{name, tech (list), summary (1 line)}}),
experience (list of {{role, org, duration, highlights (list)}}),
education (list of {{degree, institution, year, cgpa}}),
strengths (3 items),
ats_score (0-100 for ATS readiness for the target role),
suggestions (5 specific, actionable resume improvements referencing actual lines).""",
        )
        if result:
            llm_skills = [sk.canonical(s) for s in result.get("skills", []) if isinstance(s, str)]
            merged = list(dict.fromkeys(profile["skills"] + llm_skills))
            for key in ("name", "summary", "projects", "experience", "education", "strengths"):
                if result.get(key):
                    profile[key] = result[key]
            profile["skills"] = merged
            try:
                llm_score = int(float(result.get("ats_score", ats["score"])))
                ats["score"] = round((ats["score"] + max(0, min(100, llm_score))) / 2)
            except (TypeError, ValueError):
                pass
            tips = [s for s in result.get("suggestions", []) if isinstance(s, str)]
            ats["suggestions"] = list(dict.fromkeys(tips + ats["suggestions"]))[:8]

        profile["skill_categories"] = {}
        for s in profile["skills"]:
            profile["skill_categories"].setdefault(sk.category(s), []).append(s)

        ctx.state["profile"] = profile
        ctx.state["ats"] = ats
        if profile.get("name") and ctx.state.get("name") in ("", "Student", None):
            ctx.state["name"] = profile["name"]
        ctx.log(f"Profile ready: {len(profile['skills'])} skills, {len(profile['projects'])} projects. ATS {ats['score']}/100",
                kind="result")
        return [("profile.ready", {})]
