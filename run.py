import threading
import webbrowser

import uvicorn

from app import config


def check_llm():
    if not config.llm_enabled():
        print("  LLM: OFF – running in offline mode (add LLM_API_KEY to .env for AI reasoning)\n")
        return
    from app.llm import LLMUnavailable, chat_json

    print(f"  LLM: testing {config.LLM_MODEL} at {config.LLM_BASE_URL} …")
    try:
        out = chat_json("You are a health check.", 'Return {"ok": true}', max_tokens=500)
        print(f"  LLM: OK {out}\n")
    except LLMUnavailable as exc:
        print(f"  LLM: FAILED – {exc}\n  Agents will use built-in logic until this is fixed (check key / model name in .env).\n")


if __name__ == "__main__":
    url = f"http://localhost:{config.PORT}"
    print(f"\n  Placement Copilot → {url}")
    check_llm()
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.PORT, reload=False)
