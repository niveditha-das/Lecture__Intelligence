"""One LLM interface, two providers. The model is deliberately the boring,
swappable part of this system."""
from __future__ import annotations

import asyncio
import json
import os
import re
import time

from ..config import settings


# --- rate limiting ------------------------------------------------------
# Rate limiting belongs here, not in each caller. It was previously handled in
# three places with three strategies (a semaphore in verify.py, a 5s pacer in
# topics.py, a semaphore in quiz.py) and not at all in generate.py — which is
# why the eval died on 429s while topic extraction survived. One throttle at the
# single point every call passes through fixes all of them at once.
#
# The provider SDK retries 429s within milliseconds, which spends quota without
# ever succeeding. Pacing at the source is the only thing that works.
_MIN_INTERVAL = float(os.environ.get("LLM_MIN_INTERVAL", "4.5"))  # ~13 req/min
_last_call = 0.0
_pace = asyncio.Lock()


async def _throttle() -> None:
    global _last_call
    async with _pace:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()


async def _with_retries(fn, attempts: int = 4):
    """Pace every call; on 429, wait what the provider asked for and retry."""
    last: Exception | None = None
    for i in range(attempts):
        await _throttle()
        try:
            return await fn()
        except Exception as exc:
            last = exc
            if "RateLimit" not in type(exc).__name__ and "429" not in str(exc):
                raise
            await asyncio.sleep(min(60, 15 * (i + 1)))
    raise last if last else RuntimeError("no attempts made")


FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)


async def complete(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 1200,
    temperature: float = 0.2,
) -> str:
    s = settings()
    model = model or s.llm_model

    if s.llm_provider == "anthropic":
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=s.anthropic_api_key)
        resp = await _with_retries(lambda: client.messages.create(
            model=model,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": user}],
        ))
        return "".join(b.text for b in resp.content if b.type == "text")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url)
    resp = await _with_retries(lambda: client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    ))
    return resp.choices[0].message.content or ""


async def complete_json(system: str, user: str, **kw) -> dict | list:
    raw = await complete(system + "\n\nReply with JSON only. No prose, no code fences.",
                         user, **kw)
    cleaned = FENCE.sub("", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = min([i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0] or [-1])
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise
