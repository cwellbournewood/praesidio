"""Tests for the provider-specific JSON extractors.

Each provider gets its own pair of tests: ``extract`` returns the right
text + model hint, and ``inject`` round-trips a sanitised value back
into the same JSON path without disturbing other fields.
"""
from __future__ import annotations

from section_edge_proxy import extractors

# --- OpenAI ----------------------------------------------------------------

def test_openai_extract_chat_messages():
    body = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "you are a helpful agent."},
            {"role": "user", "content": "send mail to alice@example.com"},
        ],
        "temperature": 0.2,
    }
    text, model = extractors.openai_chat.extract(body)
    assert "you are a helpful agent." in text
    assert "alice@example.com" in text
    assert model == "gpt-4o"


def test_openai_extract_handles_list_content_blocks():
    body = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello there"},
                    {"type": "image_url", "image_url": {"url": "data:..."}},
                ],
            }
        ],
    }
    text, _ = extractors.openai_chat.extract(body)
    assert "hello there" in text


def test_openai_inject_round_trips():
    body = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "guard rails"},
            {"role": "user", "content": "send to alice@example.com"},
        ],
        "temperature": 0.5,
    }
    text, _ = extractors.openai_chat.extract(body)
    sanitised = text.replace("alice@example.com", "<EMAIL_A2B3>")
    extractors.openai_chat.inject(body, sanitised)

    assert body["messages"][0]["content"] == "guard rails"
    assert body["messages"][1]["content"] == "send to <EMAIL_A2B3>"
    # Untouched fields persist.
    assert body["temperature"] == 0.5
    assert body["model"] == "gpt-4o"


def test_openai_inject_preserves_block_shape():
    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "send to alice@example.com"},
                    {"type": "image_url", "image_url": {"url": "data:..."}},
                ],
            }
        ]
    }
    text, _ = extractors.openai_chat.extract(body)
    sanitised = text.replace("alice@example.com", "<EMAIL_A2B3>")
    extractors.openai_chat.inject(body, sanitised)
    # Image-url block must still be present untouched.
    assert any(b.get("type") == "image_url" for b in body["messages"][0]["content"])
    # The first text block carries the sanitised version.
    text_block = next(
        b for b in body["messages"][0]["content"] if b.get("type") in (None, "text")
    )
    assert text_block["text"] == "send to <EMAIL_A2B3>"


# --- Anthropic -------------------------------------------------------------

def test_anthropic_extract_includes_system_and_messages():
    body = {
        "model": "claude-3-5-sonnet",
        "system": "you are alice's helper",
        "messages": [
            {"role": "user", "content": "ping bob@example.com please"},
        ],
    }
    text, model = extractors.anthropic_messages.extract(body)
    assert "alice's helper" in text
    assert "bob@example.com" in text
    assert model == "claude-3-5-sonnet"


def test_anthropic_inject_round_trips_with_system_string():
    body = {
        "model": "claude-3-5-sonnet",
        "system": "you are alice's helper",
        "messages": [
            {"role": "user", "content": "ping bob@example.com please"},
        ],
    }
    text, _ = extractors.anthropic_messages.extract(body)
    sanitised = text.replace("bob@example.com", "<EMAIL_A2B3>")
    extractors.anthropic_messages.inject(body, sanitised)
    assert body["system"] == "you are alice's helper"
    assert body["messages"][0]["content"] == "ping <EMAIL_A2B3> please"


def test_anthropic_extract_with_content_blocks():
    body = {
        "model": "claude-3-5-sonnet",
        "system": "guard",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "send to bob@example.com"},
                ],
            }
        ],
    }
    text, _ = extractors.anthropic_messages.extract(body)
    assert "bob@example.com" in text


# --- Gemini ----------------------------------------------------------------

def test_gemini_extract_walks_contents_parts():
    body = {
        "systemInstruction": {"parts": [{"text": "be brief"}]},
        "contents": [
            {"role": "user", "parts": [{"text": "what is 2 + 2"}]},
            {"role": "model", "parts": [{"text": "4"}]},
        ],
    }
    text, model = extractors.gemini_generate.extract(body)
    assert "be brief" in text
    assert "what is 2 + 2" in text
    # Gemini doesn't carry model in body — extractor must return None.
    assert model is None


def test_gemini_inject_writes_to_first_text_part():
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "send to alice@example.com"},
                    {"text": "extra context"},
                ],
            }
        ],
    }
    text, _ = extractors.gemini_generate.extract(body)
    sanitised = text.replace("alice@example.com", "<EMAIL_A2B3>")
    extractors.gemini_generate.inject(body, sanitised)
    first = body["contents"][0]["parts"][0]
    assert "<EMAIL_A2B3>" in first["text"]


# --- Cohere v2 -------------------------------------------------------------

def test_cohere_v2_uses_openai_path():
    body = {
        "model": "command-r-plus",
        "messages": [{"role": "user", "content": "ping alice@example.com"}],
    }
    text, model = extractors.cohere_chat.extract(body)
    assert "alice@example.com" in text
    assert model == "command-r-plus"


# --- Cohere v1 -------------------------------------------------------------

def test_cohere_v1_message_and_history():
    body = {
        "model": "command",
        "preamble": "be helpful",
        "chat_history": [
            {"role": "USER", "message": "first turn alice@example.com"},
        ],
        "message": "follow-up bob@example.com",
    }
    text, model = extractors.cohere_chat.extract(body)
    assert "alice@example.com" in text
    assert "bob@example.com" in text
    assert "be helpful" in text
    assert model == "command"

    sanitised = text.replace("alice@example.com", "<EMAIL_A2B3>").replace(
        "bob@example.com", "<EMAIL_C7D4>"
    )
    extractors.cohere_chat.inject(body, sanitised)
    assert "<EMAIL_A2B3>" in body["chat_history"][0]["message"]
    assert "<EMAIL_C7D4>" in body["message"]


# --- Robustness ------------------------------------------------------------

def test_openai_extract_empty_messages_returns_empty_text():
    body = {"model": "gpt-4o", "messages": []}
    text, model = extractors.openai_chat.extract(body)
    assert text == ""
    assert model == "gpt-4o"


def test_openai_extract_non_dict_messages_is_safe():
    body = {"messages": "garbage"}
    text, _ = extractors.openai_chat.extract(body)
    assert text == ""


def test_anthropic_extract_no_system():
    body = {
        "messages": [{"role": "user", "content": "hi"}],
    }
    text, _ = extractors.anthropic_messages.extract(body)
    assert "hi" in text
