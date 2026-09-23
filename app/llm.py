"""
Groq LLM client — handles API calls and JSON response parsing.
"""

from __future__ import annotations

import json
import re

from groq import Groq

from app.config import GROQ_API_KEY, GROQ_MODEL, GROQ_TEMPERATURE, GROQ_MAX_TOKENS
from app.models import LLMGeneratedOutput


# Client singleton
_client: Groq | None = None


def _get_client() -> Groq:
    """Lazy-initialize the Groq client."""
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


# JSON extraction

def _extract_json(text: str) -> dict:
    """
    Extract a JSON object from the LLM response.

    Handles three common response formats:
      1. Clean JSON: {"sql": ...}
      2. Markdown-wrapped: ```json\n{...}\n```
      3. Mixed text with an embedded JSON object
    """
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if md_match:
        try:
            return json.loads(md_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Find the first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from LLM response:\n{text[:500]}")


# Public API

def generate_sql(
    system_prompt: str,
    user_message: str,
) -> LLMGeneratedOutput:
    """
    Call the Groq API and parse the structured JSON output.

    Parameters
    ----------
    system_prompt : str
        The full assembled system prompt (schema + dictionary + few-shots + feedback).
    user_message : str
        The user's natural language query (or a retry message with error context).

    Returns
    -------
    LLMGeneratedOutput
        Parsed and validated response.
    """
    client = _get_client()

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=GROQ_TEMPERATURE,
        max_tokens=GROQ_MAX_TOKENS,
        response_format={"type": "json_object"},
    )

    raw_content = response.choices[0].message.content
    parsed = _extract_json(raw_content)

    # Validate with Pydantic — raises ValidationError on bad structure
    return LLMGeneratedOutput(**parsed)
