"""OpenAI-compatible chat client — port of LLMService.swift.

Uses the official `openai` package pointed at whatever base URL the user
configured, so local servers (Ollama, llama.cpp, vLLM, LM Studio) and cloud
endpoints both work.
"""

from __future__ import annotations

import re

from openai import APIStatusError, AsyncOpenAI

# Some reasoning models prepend their scratchpad; the Swift client stripped it.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)

REQUEST_TIMEOUT_SECS = 180.0


class LLMError(RuntimeError):
    pass


async def chat(server_url: str, api_key: str, model: str, prompt: str) -> str:
    base_url = server_url.strip().rstrip("/")
    if not base_url:
        raise LLMError("No LLM server configured.")

    client = AsyncOpenAI(
        base_url=base_url,
        # Local servers usually ignore the key but the SDK requires a non-empty value.
        api_key=api_key.strip() or "not-needed",
        timeout=REQUEST_TIMEOUT_SECS,
        max_retries=0,
    )
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
    except APIStatusError as exc:
        raise LLMError(f"HTTP {exc.status_code}: {exc.message}") from exc
    except Exception as exc:  # noqa: BLE001 — surfaced to the user verbatim
        raise LLMError(str(exc)) from exc
    finally:
        await client.close()

    if not response.choices:
        raise LLMError("The LLM returned no choices.")
    content = response.choices[0].message.content or ""

    stripped = _THINK_BLOCK.sub("", content).strip()
    return stripped or content


async def list_models(server_url: str, api_key: str) -> list[str]:
    base_url = server_url.strip().rstrip("/")
    if not base_url:
        return []
    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key.strip() or "not-needed",
        timeout=10.0,
        max_retries=0,
    )
    try:
        page = await client.models.list()
        return sorted(m.id for m in page.data)
    except Exception:  # noqa: BLE001 — reachability probe, failure is not fatal
        return []
    finally:
        await client.close()
