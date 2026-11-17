"""Thin client for any OpenAI-compatible chat completions endpoint.

Every agent calls `chat_json`. If the LLM is not configured or the call fails,
it raises LLMUnavailable and the agent falls back to its deterministic logic,
so the system keeps working offline.
"""
import json
import re

import httpx

from . import config


class LLMUnavailable(Exception):
    pass


def _extract_json(text: str):
    text = text.strip()
    # Strip reasoning blocks some models emit, and markdown fences.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON object in model response")


def chat_json(system: str, user: str, temperature: float = 0.3, max_tokens: int = 6000) -> dict:
    if not config.llm_enabled():
        raise LLMUnavailable("No LLM_API_KEY configured")

    headers = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"

    body = {
        "model": config.LLM_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system + "\nRespond with a single valid JSON object only. No prose, no markdown."},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    if config.LLM_REASONING_EFFORT:
        body["reasoning_effort"] = config.LLM_REASONING_EFFORT
    url = f"{config.LLM_BASE_URL}/chat/completions"
    try:
        with httpx.Client(timeout=config.LLM_TIMEOUT) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code == 400:  # provider rejected an optional field: retry with the plain request
                body.pop("response_format", None)
                body.pop("reasoning_effort", None)
                resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"] or ""
        data = _extract_json(content)
        if not isinstance(data, dict):
            raise ValueError("Model returned non-object JSON")
        return data
    except Exception as exc:  # network, auth, rate limit, bad JSON
        raise LLMUnavailable(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
