"""Vision requests over urllib. No SDK, no proxy, no account.

build_request() is the only place payloads are shaped, so the tests can check
each provider's request without touching the network.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from deskmark.look.errors import LookError

# defaults, overridable with --model or DESKMARK_LOOK_MODEL. a short table on
# purpose: model names churn every few months and a registry that pretends
# otherwise just goes stale.
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "model": "gemini-3-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    },
    "openai": {
        "env": ["OPENAI_API_KEY"],
        "model": "gpt-5-mini",
        "url": "https://api.openai.com/v1/chat/completions",
    },
    "anthropic": {
        "env": ["ANTHROPIC_API_KEY"],
        "model": "claude-sonnet-4-5",
        "url": "https://api.anthropic.com/v1/messages",
    },
}

DEFAULT_QUESTION = "What is on this screen? Explain what the user is looking at and what they would likely do next."
MAX_IMAGE_BYTES = 8 * 1024 * 1024


@dataclass
class Answer:
    text: str
    provider: str
    model: str
    ms: int = 0
    image_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "ms": self.ms,
            "image_bytes": self.image_bytes,
        }


def detect_provider(requested: Optional[str] = None) -> str:
    """Pick a provider from the environment, preferring Gemini (cheapest vision)."""
    if requested:
        key = requested.lower().strip()
        if key not in PROVIDERS:
            raise LookError(
                "unknown provider %r" % key,
                hint="choose one of: " + ", ".join(sorted(PROVIDERS)),
            )
        if not _key_for(key):
            raise LookError(
                "no API key for %s" % key,
                hint="set " + " or ".join(PROVIDERS[key]["env"]),
            )
        return key
    for name in ("gemini", "openai", "anthropic"):
        if _key_for(name):
            return name
    raise LookError(
        "no vision provider is configured",
        hint="set GEMINI_API_KEY (cheapest), or OPENAI_API_KEY, or ANTHROPIC_API_KEY",
    )


def _key_for(provider: str) -> str:
    for name in PROVIDERS[provider]["env"]:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _encode(path: str) -> Tuple[str, str, int]:
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except FileNotFoundError as exc:
        raise LookError("no image at %s" % path) from exc
    except OSError as exc:
        raise LookError("cannot read %s: %s" % (path, exc)) from exc
    if not raw:
        raise LookError("%s is empty" % path)
    if len(raw) > MAX_IMAGE_BYTES:
        raise LookError(
            "image is %.1f MB, which is too large to send" % (len(raw) / 1048576.0),
            hint="capture a smaller region, or resize it first",
        )
    mime = "image/png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    return base64.b64encode(raw).decode("ascii"), mime, len(raw)


def build_request(
    provider: str,
    model: str,
    question: str,
    image_b64: Optional[str],
    mime: str = "image/png",
) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    """Return (url, headers, body) for one vision question."""
    key = _key_for(provider)
    if not key:
        raise LookError("no API key for %s" % provider)

    if provider == "gemini":
        url = PROVIDERS["gemini"]["url"].format(model=model) + "?key=" + key
        parts: List[Dict[str, Any]] = [{"text": question}]
        if image_b64:
            parts.append({"inline_data": {"mime_type": mime, "data": image_b64}})
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800}}
        return url, {"Content-Type": "application/json"}, body

    if provider == "openai":
        content: List[Dict[str, Any]] = [{"type": "text", "text": question}]
        if image_b64:
            content.append({"type": "image_url",
                            "image_url": {"url": "data:%s;base64,%s" % (mime, image_b64)}})
        body = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 800}
        return PROVIDERS["openai"]["url"], {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        }, body

    if provider == "anthropic":
        content = []
        if image_b64:
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": mime, "data": image_b64}})
        content.append({"type": "text", "text": question})
        body = {"model": model, "max_tokens": 800, "messages": [{"role": "user", "content": content}]}
        return PROVIDERS["anthropic"]["url"], {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }, body

    raise LookError("unknown provider %r" % provider)


def parse_response(provider: str, payload: Dict[str, Any]) -> str:
    try:
        if provider == "gemini":
            return payload["candidates"][0]["content"]["parts"][0]["text"].strip()
        if provider == "openai":
            return payload["choices"][0]["message"]["content"].strip()
        if provider == "anthropic":
            return payload["content"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        pass
    raise LookError("the provider returned an unexpected response shape")


def ask(
    question: str = DEFAULT_QUESTION,
    image: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 60,
) -> Answer:
    """Ask a vision model about one image (or the text question alone)."""
    name = detect_provider(provider)
    chosen = model or os.environ.get("DESKMARK_LOOK_MODEL") or PROVIDERS[name]["model"]
    image_b64 = mime = None
    size = 0
    if image:
        image_b64, mime, size = _encode(image)

    url, headers, body = build_request(name, chosen, question, image_b64, mime or "image/png")
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )

    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise LookError(
            "%s rejected the request (HTTP %s)" % (name, exc.code),
            hint=detail or "check the API key and the model name",
        ) from exc
    except urllib.error.URLError as exc:
        raise LookError("cannot reach %s: %s" % (name, exc.reason)) from exc
    except json.JSONDecodeError as exc:
        raise LookError("%s returned something that is not JSON" % name) from exc

    return Answer(
        text=parse_response(name, payload),
        provider=name,
        model=chosen,
        ms=int((time.time() - started) * 1000),
        image_bytes=size,
    )
