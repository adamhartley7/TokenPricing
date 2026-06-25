"""
Pre-flight INPUT token estimation — so the spend cap can be enforced before the call.

  * Anthropic: uses the free, exact `POST /v1/messages/count_tokens` endpoint. No inference, no
    charge. Falls back to the heuristic if the key/network is unavailable.
  * DeepSeek: uses the bundled HuggingFace tokenizer at vendor/deepseek_v3_tokenizer/tokenizer.json
    if present (exact); otherwise the DeepSeek-published character heuristic.

The heuristic (~0.3 token / non-CJK char, ~0.6 token / CJK char, plus a small per-message overhead)
is intentionally simple and slightly conservative; the gateway also multiplies the estimate by a
safety factor (config.estimate_safety_factor) so a low estimate still errs toward refusing.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from config import config

GATEWAY_DIR = Path(__file__).resolve().parent
_DS_TOKENIZER_PATH = GATEWAY_DIR / "vendor" / "deepseek_v3_tokenizer" / "tokenizer.json"

# Lazily-loaded HF fast tokenizer (optional dependency 'tokenizers').
_ds_tokenizer = None
_ds_tokenizer_tried = False


# ---------------------------------------------------------------------------
# Text extraction (works for both Anthropic and OpenAI/DeepSeek message shapes)
# ---------------------------------------------------------------------------
def _content_to_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # Anthropic text block {type:text,text:...}; OpenAI {type:text,text:...}
                if "text" in block:
                    parts.append(str(block["text"]))
                elif block.get("type") == "input_text" and "content" in block:
                    parts.append(str(block["content"]))
        return "\n".join(parts)
    return str(content)


def extract_text(body: dict) -> tuple[str, int]:
    """Return (all_text, message_count) from a request body, including the system prompt."""
    texts: list[str] = []
    system = body.get("system")
    if system:
        texts.append(_content_to_text(system))
    messages = body.get("messages") or []
    for m in messages:
        if isinstance(m, dict):
            texts.append(_content_to_text(m.get("content")))
    # Tools add tokens too; include their JSON-ish text crudely.
    tools = body.get("tools")
    if tools:
        texts.append(str(tools))
    return "\n".join(texts), len(messages)


# ---------------------------------------------------------------------------
# Heuristic
# ---------------------------------------------------------------------------
def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF      # CJK Unified Ideographs
        or 0x3040 <= o <= 0x30FF   # Hiragana + Katakana
        or 0xAC00 <= o <= 0xD7AF   # Hangul
        or 0x3400 <= o <= 0x4DBF   # CJK Extension A
    )


def heuristic_tokens(body: dict) -> int:
    text, n_messages = extract_text(body)
    cjk = sum(1 for ch in text if _is_cjk(ch))
    other = len(text) - cjk
    est = other * 0.3 + cjk * 0.6
    est += n_messages * 4          # per-message role/format overhead
    est += 8                       # request envelope overhead
    return max(1, int(est + 0.5))


# ---------------------------------------------------------------------------
# DeepSeek exact (optional)
# ---------------------------------------------------------------------------
def _load_ds_tokenizer():
    global _ds_tokenizer, _ds_tokenizer_tried
    if _ds_tokenizer_tried:
        return _ds_tokenizer
    _ds_tokenizer_tried = True
    if _DS_TOKENIZER_PATH.exists():
        try:
            from tokenizers import Tokenizer  # optional dep
            _ds_tokenizer = Tokenizer.from_file(str(_DS_TOKENIZER_PATH))
        except Exception:
            _ds_tokenizer = None
    return _ds_tokenizer


def deepseek_tokens(body: dict) -> int:
    tok = _load_ds_tokenizer()
    if tok is None:
        return heuristic_tokens(body)
    text, n_messages = extract_text(body)
    try:
        n = len(tok.encode(text).ids)
        return max(1, n + n_messages * 4 + 8)
    except Exception:
        return heuristic_tokens(body)


# ---------------------------------------------------------------------------
# Anthropic exact (free count_tokens endpoint)
# ---------------------------------------------------------------------------
async def anthropic_tokens(body: dict) -> int:
    key = config.anthropic_key
    if not key:
        return heuristic_tokens(body)
    payload = {"model": body.get("model"), "messages": body.get("messages", [])}
    if body.get("system") is not None:
        payload["system"] = body["system"]
    if body.get("tools") is not None:
        payload["tools"] = body["tools"]
    headers = {
        "x-api-key": key,
        "anthropic-version": config.anthropic_version,
        "content-type": "application/json",
    }
    url = f"{config.anthropic_base}/v1/messages/count_tokens"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return int(r.json()["input_tokens"])
    except Exception:
        # Network/auth/shape problem — fall back rather than fail the whole request here;
        # the cap is still enforced on the (conservative) heuristic estimate.
        return heuristic_tokens(body)


async def estimate_input_tokens(provider: str, body: dict) -> int:
    """Best available pre-flight input-token estimate for a provider."""
    if provider == "anthropic":
        return await anthropic_tokens(body)
    if provider == "deepseek":
        return deepseek_tokens(body)
    return heuristic_tokens(body)
