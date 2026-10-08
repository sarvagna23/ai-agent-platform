"""The LLM step: build a grounded prompt and call Claude."""
import os
from functools import lru_cache

from app import config


class LLMUnavailable(Exception):
    """The model cannot be called, for example because no API key is configured."""


SYSTEM_PROMPT = (
    "You answer questions using only the context provided. "
    "If the context does not contain the answer, say you do not know. "
    "Keep the answer under 120 words and cite the titles you used in square brackets."
)


def build_prompt(question: str, contexts: list[dict]) -> str:
    """Put the retrieved documents and the question into one prompt."""
    context_blocks = [f"[{item['title']}]\n{item['content']}" for item in contexts]
    joined_context = "\n\n".join(context_blocks)
    return f"Context:\n{joined_context}\n\nQuestion: {question}"


@lru_cache(maxsize=1)
def _get_client():
    """Create the Anthropic client once. Raises LLMUnavailable when there is no API key."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=api_key)


def _echo_answer(contexts: list[dict]) -> dict:
    """Load-test mode: no model call, so no tokens are spent."""
    titles = ", ".join(item["title"] for item in contexts)
    return {"text": f"[echo mode] Closest sources: {titles}", "input_tokens": 0, "output_tokens": 0}


async def generate_answer(question: str, contexts: list[dict]) -> dict:
    """Return {'text', 'input_tokens', 'output_tokens'} for the question and its context."""
    if config.LLM_MODE == "echo":
        return _echo_answer(contexts)

    client = _get_client()
    response = await client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(question, contexts)}],
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return {
        "text": "".join(text_blocks).strip(),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
