from .. import db
from ..llm import LLMUnavailable, chat_json


class AgentContext:
    """What an agent sees while handling one event: the shared student state and a logger."""

    def __init__(self, sid: str, state: dict, agent_name: str):
        self.sid = sid
        self.state = state
        self.agent_name = agent_name

    def log(self, message: str, kind: str = "info", data=None):
        db.log_event(self.sid, self.agent_name, kind, message, data)


class Agent:
    name = "agent"
    label = "Agent"
    description = ""
    subscribes: list[str] = []

    def handle(self, ctx: AgentContext, event: str, payload: dict) -> list[tuple[str, dict]]:
        """Process an event, mutate ctx.state, and return follow-up events for the orchestrator."""
        raise NotImplementedError

    def think(self, ctx: AgentContext, purpose: str, system: str, user: str, **kw):
        """Ask the LLM; return None (and log the fallback) if it is unavailable."""
        ctx.log(f"Reasoning with LLM: {purpose}", kind="llm")
        try:
            return chat_json(system, user, **kw)
        except LLMUnavailable as exc:
            ctx.log(f"LLM unavailable ({exc}); using built-in logic", kind="fallback")
            return None
