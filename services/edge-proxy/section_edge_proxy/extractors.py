"""Provider-specific JSON extractors.

Each extractor pulls user-supplied prompt text out of a provider's
request JSON (so we can hand it to ``/v1/scan``) and re-injects the
sanitised text into the same JSON path so the rest of the request still
validates against the provider's schema.

Pattern: every extractor implements :func:`Extractor` — ``extract(body)``
returns ``(prompt_text, model)``, and ``inject(body, sanitised)`` returns
the mutated body. Response-side restoration walks the response JSON for
placeholders separately (no provider-specific hook needed because the
response side is just text replacement on the bytes).
"""
from __future__ import annotations

from typing import Any, Protocol


class Extractor(Protocol):
    """Provider extractor contract."""

    def extract(self, body: dict[str, Any]) -> tuple[str, str | None]:
        """Return ``(prompt_text, model_hint)`` from the request body.

        ``prompt_text`` is what we send to ``/v1/scan``. If the request
        carries multiple messages, return them joined with a stable
        separator so token boundaries are unambiguous on rewrite.
        ``model_hint`` is the provider model id if the body carries one.
        Returns ``("", None)`` if the body has no prompt-shaped content.
        """
        ...  # pragma: no cover - protocol

    def inject(self, body: dict[str, Any], sanitised: str) -> dict[str, Any]:
        """Re-inject *sanitised* into the request body, returning it.

        Must preserve every other field on *body* unchanged. The same
        message boundaries used by :meth:`extract` are used to split
        ``sanitised`` back into the original shape (we re-tokenise on
        the same separator).
        """
        ...  # pragma: no cover - protocol


# Stable separator we splice between messages for round-tripping. Picked
# so it (a) never appears in user text and (b) never matches the
# placeholder grammar `<LABEL_XXXX>` so an extractor can't collide with
# a sanitised placeholder.
_SEP = "\x1e\x1e--SECTION-SEP--\x1e\x1e"


def _split(sanitised: str, n: int) -> list[str]:
    """Split *sanitised* back into *n* parts on the message separator.

    The scan endpoint never changes the separator (it's outside any
    placeholder), so a simple split is round-trip safe. If the gateway
    somehow returns fewer parts (e.g. the separator was lost), we pad
    with empty strings rather than crash — the request will be
    semantically broken but won't 500.
    """
    parts = sanitised.split(_SEP)
    if len(parts) < n:
        parts = parts + [""] * (n - len(parts))
    elif len(parts) > n:
        # Re-join the overflow back onto the last slot.
        head = parts[: n - 1]
        tail = _SEP.join(parts[n - 1 :])
        parts = head + [tail]
    return parts


class _OpenAIChat:
    """OpenAI-compatible /v1/chat/completions shape.

    Also serves Mistral, Perplexity, Groq, DeepSeek — they all clone
    OpenAI's chat-completions schema. Handles both string content and
    the newer ``content: [{type: "text", text: "..."}]`` array form.
    """

    def extract(self, body: dict[str, Any]) -> tuple[str, str | None]:
        messages = body.get("messages") or []
        if not isinstance(messages, list):
            return "", body.get("model")
        chunks: list[str] = []
        for m in messages:
            if not isinstance(m, dict):
                chunks.append("")
                continue
            content = m.get("content")
            chunks.append(_flatten_content(content))
        return _SEP.join(chunks), body.get("model")

    def inject(self, body: dict[str, Any], sanitised: str) -> dict[str, Any]:
        messages = body.get("messages") or []
        if not isinstance(messages, list) or not messages:
            return body
        parts = _split(sanitised, len(messages))
        for m, part in zip(messages, parts, strict=False):
            if not isinstance(m, dict):
                continue
            _rewrite_content(m, part)
        return body


class _AnthropicMessages:
    """Anthropic /v1/messages shape.

    Has a top-level ``system`` (string) + ``messages[].content`` which
    may be a string or a list of content blocks each with ``{type:"text",text:"..."}``.
    """

    def extract(self, body: dict[str, Any]) -> tuple[str, str | None]:
        chunks: list[str] = []
        sys_val = body.get("system")
        if isinstance(sys_val, str):
            chunks.append(sys_val)
        elif isinstance(sys_val, list):
            # Anthropic also accepts a list of system blocks.
            chunks.append(_flatten_content(sys_val))
        else:
            chunks.append("")

        messages = body.get("messages") or []
        if isinstance(messages, list):
            for m in messages:
                if not isinstance(m, dict):
                    chunks.append("")
                    continue
                chunks.append(_flatten_content(m.get("content")))
        return _SEP.join(chunks), body.get("model")

    def inject(self, body: dict[str, Any], sanitised: str) -> dict[str, Any]:
        messages = body.get("messages") or []
        if not isinstance(messages, list):
            messages = []
        parts = _split(sanitised, 1 + len(messages))

        sys_part = parts[0]
        if isinstance(body.get("system"), list):
            # Replace text blocks one-by-one.
            _rewrite_list_text(body["system"], sys_part)
        elif "system" in body:
            body["system"] = sys_part

        for m, part in zip(messages, parts[1:], strict=False):
            if not isinstance(m, dict):
                continue
            _rewrite_content(m, part)
        return body


class _GeminiGenerate:
    """Gemini generativelanguage v1beta shape.

    Body has ``contents: [{role, parts: [{text: "..."}]}, ...]`` and
    optionally a top-level ``systemInstruction: {parts: [{text: "..."}]}``.
    """

    def extract(self, body: dict[str, Any]) -> tuple[str, str | None]:
        chunks: list[str] = []
        sys_inst = body.get("systemInstruction") or body.get("system_instruction")
        if isinstance(sys_inst, dict):
            sys_parts = sys_inst.get("parts") or []
            chunks.append(_join_text_parts(sys_parts))
        else:
            chunks.append("")

        contents = body.get("contents") or []
        if isinstance(contents, list):
            for c in contents:
                if not isinstance(c, dict):
                    chunks.append("")
                    continue
                chunks.append(_join_text_parts(c.get("parts") or []))
        return _SEP.join(chunks), None

    def inject(self, body: dict[str, Any], sanitised: str) -> dict[str, Any]:
        contents = body.get("contents") or []
        if not isinstance(contents, list):
            contents = []
        parts = _split(sanitised, 1 + len(contents))

        sys_inst = body.get("systemInstruction") or body.get("system_instruction")
        if isinstance(sys_inst, dict):
            _rewrite_text_parts(sys_inst.get("parts") or [], parts[0])
        for c, part in zip(contents, parts[1:], strict=False):
            if not isinstance(c, dict):
                continue
            _rewrite_text_parts(c.get("parts") or [], part)
        return body


class _CohereChat:
    """Cohere /v1/chat + /v2/chat shapes.

    v2 mirrors OpenAI's ``messages[].content``; v1 uses ``message`` plus
    ``chat_history: [{role, message}]``. We support both.
    """

    def extract(self, body: dict[str, Any]) -> tuple[str, str | None]:
        # v2: messages[]
        if isinstance(body.get("messages"), list):
            return _OpenAIChat().extract(body)

        chunks: list[str] = []
        chat_history = body.get("chat_history") or []
        if isinstance(chat_history, list):
            for h in chat_history:
                if isinstance(h, dict):
                    chunks.append(str(h.get("message", "")))
                else:
                    chunks.append("")
        chunks.append(str(body.get("message", "")))
        # v1 also has a `preamble` (system-prompt) field.
        chunks.insert(0, str(body.get("preamble", "")))
        return _SEP.join(chunks), body.get("model")

    def inject(self, body: dict[str, Any], sanitised: str) -> dict[str, Any]:
        if isinstance(body.get("messages"), list):
            return _OpenAIChat().inject(body, sanitised)

        chat_history = body.get("chat_history") or []
        if not isinstance(chat_history, list):
            chat_history = []
        parts = _split(sanitised, 1 + len(chat_history) + 1)
        body["preamble"] = parts[0]
        for h, part in zip(chat_history, parts[1:-1], strict=False):
            if isinstance(h, dict):
                h["message"] = part
        body["message"] = parts[-1]
        return body


# --- Helpers ---------------------------------------------------------------

def _flatten_content(content: Any) -> str:
    """Reduce an OpenAI/Anthropic content field to a single text string.

    Accepts a bare string, a list of content blocks
    (``[{"type":"text","text":"..."}, {"type":"image_url", ...}]``),
    or anything else (returns "").
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    out.append(t)
        return "\n".join(out)
    return ""


def _rewrite_content(message: dict[str, Any], new_text: str) -> None:
    """Set *message*'s content to *new_text*, preserving its original shape."""
    content = message.get("content")
    if isinstance(content, str) or content is None:
        message["content"] = new_text
        return
    if isinstance(content, list):
        _rewrite_list_text(content, new_text)
        return
    message["content"] = new_text


def _rewrite_list_text(blocks: list[Any], new_text: str) -> None:
    """Concentrate *new_text* into the first text block; clear the rest.

    Why: we don't know how to split sanitised text back across multiple
    text blocks within a single message (the gateway returns one string
    per message). The simplest faithful representation is "all
    sanitised text in the first text block, others left empty". This is
    semantically identical for the LLM but preserves the block schema.
    """
    first_done = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") not in (None, "text"):
            continue
        if "text" not in block and "type" not in block:
            continue
        if not first_done:
            block["text"] = new_text
            first_done = True
        else:
            block["text"] = ""
    if not first_done and blocks is not None:
        blocks.append({"type": "text", "text": new_text})


def _join_text_parts(parts: list[Any]) -> str:
    """Concatenate ``text`` fields of a Gemini parts array."""
    out: list[str] = []
    for p in parts:
        if isinstance(p, dict):
            t = p.get("text")
            if isinstance(t, str):
                out.append(t)
    return "\n".join(out)


def _rewrite_text_parts(parts: list[Any], new_text: str) -> None:
    """Concentrate *new_text* into the first text part."""
    first_done = False
    for p in parts:
        if not isinstance(p, dict):
            continue
        if "text" not in p:
            continue
        if not first_done:
            p["text"] = new_text
            first_done = True
        else:
            p["text"] = ""
    if not first_done:
        parts.append({"text": new_text})


# --- Public exports --------------------------------------------------------

openai_chat: Extractor = _OpenAIChat()
anthropic_messages: Extractor = _AnthropicMessages()
gemini_generate: Extractor = _GeminiGenerate()
cohere_chat: Extractor = _CohereChat()

__all__ = [
    "Extractor",
    "openai_chat",
    "anthropic_messages",
    "gemini_generate",
    "cohere_chat",
]
