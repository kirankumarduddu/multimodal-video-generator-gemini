"""Google Cloud clients (Vertex AI through google-genai, Application Default Credentials) and retries."""
from __future__ import annotations

import base64
import functools
import time
from typing import Any, Callable, TypeVar

from .project import Project

T = TypeVar("T")
RETRYABLE = {408, 429, 500, 502, 503, 504}


@functools.lru_cache(maxsize=16)
def _client(project: str, location: str):
    from google import genai

    return genai.Client(vertexai=True, project=project, location=location)


def client(project: Project, kind: str):
    return _client(project.gcp_project, project.model(kind).get("location", "global"))


def status_code(error: Exception) -> int | None:
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    return code if isinstance(code, int) else None


def retry(call: Callable[[], T], label: str, attempts: int = 5, base: float = 15.0) -> T:
    """Retry rate limits and transient server errors with a growing wait; other errors surface at once."""
    for attempt in range(attempts):
        try:
            return call()
        except Exception as error:  # noqa: BLE001 - the SDK raises several error types
            code = status_code(error)
            if code not in RETRYABLE or attempt == attempts - 1:
                raise
            wait = base * (attempt + 1)
            print(f"  {label}: HTTP {code}, retrying in {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


def first_inline(response: Any) -> bytes | None:
    """The first inline image or audio part of a generate_content response."""
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            data = getattr(getattr(part, "inline_data", None), "data", None)
            if data:
                return data if isinstance(data, bytes) else base64.b64decode(data)
    return None


def wait_interaction(api: Any, interaction: Any, label: str, poll: float = 10.0, timeout: float = 1200.0) -> Any:
    """Poll an Interactions API job (Omni video, Lyria music) until it ends."""
    started = time.monotonic()
    while getattr(interaction, "status", None) not in ("completed", "failed", "cancelled", "incomplete"):
        if time.monotonic() - started > timeout:
            raise TimeoutError(f"{label}: still {interaction.status} after {timeout:.0f}s")
        time.sleep(poll)
        interaction = api.interactions.get(id=interaction.id)
    return interaction
