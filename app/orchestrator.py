"""Event-driven orchestrator.

Agents never call each other directly. Each agent handles an event, updates the
shared student state, and emits follow-up events. The orchestrator routes every
event to the agents subscribed to it, persists state after each step, and logs a
trace that the UI renders live.

    resume.uploaded ─► Resume Analyst ─► profile.ready ─► Job Scout ─► jobs.ranked
      ─► Skill Gap Analyzer ─► gaps.identified ─► Roadmap Planner ─► roadmap.ready
      ─► Progress Tracker

    interview.answered ─► Mock Interviewer ─► interview.evaluated ─► Progress Tracker
      ─► weak_topics.detected ─► Roadmap Planner ─► roadmap.revised ─► Progress Tracker
"""
import os
import threading
import time
import traceback
from collections import defaultdict, deque

from . import config, db
from .agents.gap_agent import SkillGapAgent
from .agents.interview_agent import InterviewAgent
from .agents.job_agent import JobScoutAgent
from .agents.progress_agent import ProgressAgent
from .agents.resume_agent import ResumeAgent
from .agents.roadmap_agent import RoadmapAgent

MAX_STEPS = 25
# In offline mode agents finish instantly; a short pause keeps the hand-offs visible in the UI.
OFFLINE_STEP_DELAY = float(os.getenv("OFFLINE_STEP_DELAY", "0.7"))


class Orchestrator:
    def __init__(self):
        self.agents = {a.name: a for a in [ResumeAgent(), JobScoutAgent(), SkillGapAgent(),
                                           RoadmapAgent(), InterviewAgent(), ProgressAgent()]}
        self.routes = defaultdict(list)
        for agent in self.agents.values():
            for ev in agent.subscribes:
                self.routes[ev].append(agent.name)
        self._locks = defaultdict(threading.Lock)
        self._pending = defaultdict(int)
        self._pending_lock = threading.Lock()

    # ---- public API -------------------------------------------------------
    def is_busy(self, sid: str) -> bool:
        return self._pending[sid] > 0

    def submit(self, sid: str, event: str, payload: dict | None = None):
        """Run an event chain in the background; the UI polls state + events."""
        with self._pending_lock:
            self._pending[sid] += 1
        threading.Thread(target=self._run, args=(sid, event, payload or {}), daemon=True).start()

    def describe(self) -> dict:
        return {
            "agents": [{"name": a.name, "label": a.label, "description": a.description, "subscribes": a.subscribes}
                       for a in self.agents.values()],
            "routes": dict(self.routes),
        }

    # ---- internals --------------------------------------------------------
    def _run(self, sid, event, payload):
        try:
            self.dispatch(sid, event, payload)
        finally:
            with self._pending_lock:
                self._pending[sid] -= 1

    def dispatch(self, sid: str, event: str, payload: dict):
        with self._locks[sid]:
            state = db.get_state(sid)
            if state is None:
                return
            state["status"] = "running"
            db.save_state(sid, state)
            db.log_event(sid, "orchestrator", "event", f"Event received: {event}")
            queue = deque([(event, payload)])
            steps = 0
            t_start = time.time()
            try:
                while queue:
                    ev, pl = queue.popleft()
                    targets = self.routes.get(ev, [])
                    if not targets:
                        continue
                    for name in targets:
                        steps += 1
                        if steps > MAX_STEPS:
                            raise RuntimeError("Step limit reached — possible event loop")
                        agent = self.agents[name]
                        db.log_event(sid, "orchestrator", "route", f"{ev} → {agent.label}")
                        t0 = time.time()
                        if not config.llm_enabled():
                            time.sleep(OFFLINE_STEP_DELAY)
                        emitted = agent.handle(_ctx(sid, state, name), ev, pl) or []
                        db.save_state(sid, state)
                        db.log_event(sid, name, "done", f"{agent.label} finished in {time.time() - t0:.1f}s"
                                     + (f"; emitted {', '.join(e for e, _ in emitted)}" if emitted else ""))
                        queue.extend(emitted)
                state["status"] = "ready"
                db.log_event(sid, "orchestrator", "complete",
                             f"Workflow complete: {steps} agent step{'s' if steps != 1 else ''} in {time.time() - t_start:.1f}s")
            except Exception as exc:
                state["status"] = "error"
                db.log_event(sid, "orchestrator", "error", f"{type(exc).__name__}: {exc}", {"trace": traceback.format_exc()[-1500:]})
            db.save_state(sid, state)


def _ctx(sid, state, name):
    from .agents.base import AgentContext

    return AgentContext(sid, state, name)


orchestrator = Orchestrator()
