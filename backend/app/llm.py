"""Gemma 4 chat calls over OpenAI-compatible endpoints, with hedging.

The same Gemma 4 model family is served by several hosts, each of which
sometimes queues or rejects requests under load (free tiers). A call starts on
the first configured host; if it has not answered after `hedge_after_seconds`
(or fails), the next host is started in parallel. The first valid answer wins.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass

import httpx

from .config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    model: str
    key_env: str
    max_images: int
    timeout: int = 25   # seconds; a hung request is retried, not waited on


PROVIDERS = {
    "nvidia": Provider("nvidia", "https://integrate.api.nvidia.com/v1/chat/completions",
                       os.environ.get("EVIDENCE_NVIDIA_MODEL", "google/gemma-4-31b-it"),
                       "NVIDIA_API_KEY", 4, 60),
    "google": Provider("google",
                       "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                       os.environ.get("EVIDENCE_MODEL", "gemma-4-26b-a4b-it"),
                       "GEMINI_API_KEY", 16, 45),
    "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1/chat/completions",
                           os.environ.get("EVIDENCE_OPENROUTER_MODEL", "google/gemma-4-31b-it:free"),
                           "OPENROUTER_KEY", 8),
    # Last resort when every Gemma 4 host is overloaded.
    "google-flash": Provider("google-flash",
                             "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                             os.environ.get("EVIDENCE_FALLBACK_MODEL", "gemini-flash-latest"),
                             "GEMINI_API_KEY", 16, 30),
}
TRANSIENT = {408, 409, 425, 429, 500, 502, 503, 504, 529}
DEADLINE_SECONDS = 150


class LLMError(Exception):
    pass


class TransientError(LLMError):
    pass


def available_providers() -> list[Provider]:
    order = os.environ.get("EVIDENCE_PROVIDERS", "nvidia,google,openrouter,google-flash")
    out = []
    for name in (n.strip() for n in order.split(",")):
        p = PROVIDERS.get(name)
        if p and os.environ.get(p.key_env):
            out.append(p)
    return out


def _race_order(providers: list[Provider]) -> list[Provider]:
    """Order in which hosts join a race.

    A free host's latency is mostly queueing (the same call takes 3 s or
    110 s), so a second identical request to the first host usually beats
    waiting on the first. Hosts alternate: A, B, A, C, A, D ...
    """
    if len(providers) < 1:
        return []
    first, rest = providers[0], providers[1:]
    order = [first]
    for p in rest or [first]:
        order += [p, first]
    return order


def image_part(png: bytes) -> dict:
    return {"type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def _clean(text: str) -> str:
    text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.S)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.strip()


def parse_json(text: str) -> dict:
    text = _clean(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        # Some replies drop the braces: 'found: false, answer: ...'.
        m = re.match(r'\s*"?found"?\s*[:=]\s*false\W+"?answer"?\s*[:=]\s*"?(.*?)"?\s*$', text, re.S | re.I)
        if m:
            return {"found": False, "answer": m.group(1), "citations": []}
        raise LLMError("model did not return JSON")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"model returned invalid JSON: {exc}") from exc


def _call(provider: Provider, content: list[dict], max_tokens: int) -> tuple[str, str]:
    images = sum(1 for c in content if c["type"] == "image_url")
    if images > provider.max_images:
        raise LLMError(f"{provider.name} accepts at most {provider.max_images} images")
    start = time.monotonic()
    try:
        resp = httpx.post(
            provider.url,
            headers={"Authorization": f"Bearer {os.environ[provider.key_env]}"},
            # Google-hosted Gemma spends output tokens on a <thought> block first.
            json={"model": provider.model, "temperature": 0,
                  "max_tokens": max_tokens * (4 if provider.name.startswith("google") else 1),
                  "messages": [{"role": "user", "content": content}]},
            timeout=httpx.Timeout(provider.timeout, connect=10),
        )
    except httpx.HTTPError as exc:
        raise TransientError(f"{provider.name}: {exc}") from exc
    if resp.status_code != 200:
        cls = TransientError if resp.status_code in TRANSIENT else LLMError
        raise cls(f"{provider.name} HTTP {resp.status_code}: {resp.text[:160]}")
    text = resp.json()["choices"][0]["message"].get("content") or ""
    log.info("%s answered in %.1fs", provider.name, time.monotonic() - start)
    return text, f"{provider.name}:{provider.model}"


def complete_json(content: list[dict], max_tokens: int = 1200,
                  deadline_seconds: float = DEADLINE_SECONDS) -> tuple[dict, str]:
    """Run a prompt and return (parsed JSON, "provider:model")."""
    providers = available_providers()
    if not providers:
        raise LLMError("No model API key is configured. Add NVIDIA_API_KEY or GEMINI_API_KEY to .env.")
    settings = get_settings()
    errors: list[str] = []
    deadline = time.monotonic() + deadline_seconds
    finished = False

    def run(p: Provider) -> tuple[dict, str]:
        # Retry overloads/rate limits on this host until the shared deadline.
        attempt = 0
        while True:
            try:
                text, used = _call(p, content, max_tokens)
                try:
                    return parse_json(text), used
                except LLMError:
                    log.warning("%s returned unparseable output: %r", p.name, text[-300:])
                    raise
            except TransientError as exc:
                log.info("%s transient failure (attempt %d): %s", p.name, attempt + 1, str(exc)[:160])
                attempt += 1
                if finished or time.monotonic() + 4 * attempt > deadline - 10:
                    raise
                # Rate limits clear slowly; back off harder than for overloads.
                time.sleep(min((8 if "429" in str(exc) else 4) * attempt, 15))
                if finished:  # another host already answered
                    raise
            except LLMError:
                attempt += 1
                if attempt >= 2 or finished:  # one retry for malformed output
                    raise

    queue = _race_order(providers)
    pool = ThreadPoolExecutor(max_workers=len(queue))
    try:
        pending = {}
        # Free hosts queue unpredictably (3 s one call, 110 s the next), so
        # two requests race from the start and another joins periodically.
        for _ in range(min(2, len(queue))):
            pending[pool.submit(run, queue.pop(0))] = True
        while pending and time.monotonic() < deadline:
            done, _ = wait(list(pending), timeout=min(settings.hedge_after_seconds,
                                                      max(0.1, deadline - time.monotonic())),
                           return_when=FIRST_COMPLETED)
            for fut in done:
                pending.pop(fut)
                try:
                    return fut.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))
                    log.warning("provider failed: %s", exc)
            # Timed out or a host failed: add the next host in parallel.
            if queue:
                pending[pool.submit(run, queue.pop(0))] = True
        raise LLMError("All model providers failed: " + " | ".join(errors))
    finally:
        finished = True  # noqa: F841 - read by run() through its closure
        pool.shutdown(wait=False, cancel_futures=True)
