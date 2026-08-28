"""One LLM interface, two providers. The model is deliberately the boring,
swappable part of this system."""
from __future__ import annotations

import json
import re

from ..config import settings

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
        resp = await client.messages.create(
            model=model,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url)
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
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
