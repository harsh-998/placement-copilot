import io

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db
from .orchestrator import orchestrator

app = FastAPI(title="Placement Copilot – Multi-Agent API", version="1.0")
STATIC = config.ROOT / "static"


class NewStudent(BaseModel):
    name: str = "Student"
    target_role: str = "Software Engineer"


class TargetIn(BaseModel):
    job_id: str


class RoadmapIn(BaseModel):
    weeks: int = 4


class TaskIn(BaseModel):
    done: bool


class InterviewStart(BaseModel):
    mode: str = "technical"
    count: int = 5


class AnswerIn(BaseModel):
    index: int
    answer: str


def _state_or_404(sid: str) -> dict:
    st = db.get_state(sid)
    if st is None:
        raise HTTPException(404, "Student not found")
    return st


def _extract_text(upload: UploadFile) -> str:
    data = upload.file.read()
    name = (upload.filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        import docx

        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs)
    return data.decode("utf-8", errors="ignore")


@app.get("/api/config")
def get_config():
    return {"llm_enabled": config.llm_enabled(), "model": config.LLM_MODEL if config.llm_enabled() else None,
            "live_jobs": bool(config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY), **orchestrator.describe()}


@app.get("/api/sample-resume")
def sample_resume():
    return {"text": (config.ROOT / "sample_resume.txt").read_text()}


@app.get("/api/students")
def students():
    return db.list_students()


@app.post("/api/students")
def create_student(body: NewStudent):
    sid = db.create_student(body.name.strip() or "Student", body.target_role.strip() or "Software Engineer")
    db.log_event(sid, "orchestrator", "event", f"Student workspace created for {body.name} (target: {body.target_role})")
    return {"id": sid}


@app.get("/api/students/{sid}")
def get_student(sid: str):
    st = _state_or_404(sid)
    st.pop("resume_text", None)
    if orchestrator.is_busy(sid):
        st["status"] = "running"
    return st


@app.get("/api/students/{sid}/events")
def events(sid: str, after: int = 0):
    return db.get_events(sid, after)


@app.post("/api/students/{sid}/resume")
def upload_resume(sid: str, file: UploadFile | None = File(None), text: str = Form(""), target_role: str = Form("")):
    st = _state_or_404(sid)
    content = _extract_text(file) if file and file.filename else text
    if len(content.split()) < 30:
        raise HTTPException(400, "Could not read enough text from the resume. Try a text-based PDF/DOCX or paste the text.")
    if target_role.strip():
        st["target_role"] = target_role.strip()
        db.save_state(sid, st)
    orchestrator.submit(sid, "resume.uploaded", {"text": content})
    return {"ok": True}


def _require(st, key, msg):
    if not st.get(key):
        raise HTTPException(400, msg)


@app.post("/api/students/{sid}/target")
def set_target(sid: str, body: TargetIn):
    _require(_state_or_404(sid), "jobs", "Upload a resume first")
    orchestrator.submit(sid, "target.selected", {"job_id": body.job_id})
    return {"ok": True}


@app.post("/api/students/{sid}/roadmap")
def regenerate_roadmap(sid: str, body: RoadmapIn):
    _require(_state_or_404(sid), "gaps", "Run skill-gap analysis first")
    orchestrator.submit(sid, "roadmap.regenerate", {"weeks": max(2, min(12, body.weeks))})
    return {"ok": True}


@app.post("/api/students/{sid}/tasks/{task_id}")
def toggle_task(sid: str, task_id: str, body: TaskIn):
    _require(_state_or_404(sid), "roadmap", "No roadmap yet")
    orchestrator.submit(sid, "task.toggled", {"task_id": task_id, "done": body.done})
    return {"ok": True}


@app.post("/api/students/{sid}/interview/start")
def interview_start(sid: str, body: InterviewStart):
    _require(_state_or_404(sid), "profile", "Upload a resume first")
    mode = body.mode if body.mode in ("technical", "hr") else "technical"
    orchestrator.submit(sid, "interview.requested", {"mode": mode, "count": max(3, min(8, body.count))})
    return {"ok": True}


@app.post("/api/students/{sid}/interview/answer")
def interview_answer(sid: str, body: AnswerIn):
    st = _state_or_404(sid)
    _require(st, "active_interview", "No active interview")
    orchestrator.submit(sid, "interview.answered", {"index": body.index, "answer": body.answer})
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
