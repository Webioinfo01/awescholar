"""LiteLLM wrapper for multi-provider LLM calls with structured output."""

import json
import re

import litellm
from pydantic import BaseModel

from .utils import retry_with_backoff


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown fences and preamble."""
    # Try direct parse first
    text = text.strip()
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    # Strip ```json ... ``` fences
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            pass

    # Find first { ... } or [ ... ] block
    for pattern in [r"\{.*\}", r"\[.*\]"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                json.loads(candidate)
                return candidate
            except (json.JSONDecodeError, ValueError):
                pass

    return text


def complete(
    model: str,
    system: str,
    user: str,
    response_format: type[BaseModel] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
) -> BaseModel | str:
    """Call LLM with optional structured output.

    Uses {"type": "json_object"} for broad provider compatibility instead of
    native structured outputs (which many providers don't support).
    Extracts and validates JSON from the response post-hoc.

    If response_format is provided, returns validated Pydantic model.
    Otherwise returns raw string content.
    """
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["api_base"] = base_url
    if response_format:
        kwargs["response_format"] = {"type": "json_object"}

    response = retry_with_backoff(litellm.completion, **kwargs)
    content = response.choices[0].message.content

    if response_format:
        cleaned = _extract_json(content)
        return response_format.model_validate_json(cleaned)
    return content
