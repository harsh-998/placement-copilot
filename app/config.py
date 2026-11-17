import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Any OpenAI-compatible chat endpoint works (Groq, Gemini, OpenAI, OpenRouter, Ollama...).
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
# "low" keeps reasoning models (gpt-oss, Gemini 2.5) fast. Leave empty for models that do not support it.
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "").strip()
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))

# Optional live job source (https://developer.adzuna.com). Sample listings are used otherwise.
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "").strip()
ADZUNA_COUNTRY = os.getenv("ADZUNA_COUNTRY", "in")

DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "copilot.db")))
PORT = int(os.getenv("PORT", "8000"))


def llm_enabled() -> bool:
    return bool(LLM_API_KEY) or "localhost" in LLM_BASE_URL or "127.0.0.1" in LLM_BASE_URL
