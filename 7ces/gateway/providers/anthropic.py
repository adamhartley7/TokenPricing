"""Anthropic (Claude) adapter — native Messages API shape."""
from __future__ import annotations

from config import config
from providers.base import Provider, StreamAccumulator


class _AnthropicStream(StreamAccumulator):
    """
    Anthropic SSE: `message_start` carries input (+cache) usage; each `message_delta` carries the
    cumulative output_tokens; `message_stop` ends it.
    """

    def feed(self, data_obj: dict) -> None:
        t = data_obj.get("type")
        if t == "message_start":
            u = (data_obj.get("message") or {}).get("usage") or {}
            self.usage = dict(u)
        elif t == "message_delta":
            u = data_obj.get("usage") or {}
            if self.usage is None:
                self.usage = {}
            # message_delta.usage.output_tokens is cumulative; take the latest.
            for key in ("output_tokens", "input_tokens",
                        "cache_creation_input_tokens", "cache_read_input_tokens"):
                if key in u:
                    self.usage[key] = u[key]


class AnthropicProvider(Provider):
    name = "anthropic"
    max_tokens_field = "max_tokens"

    def auth_headers(self, incoming: dict[str, str]) -> dict[str, str]:
        headers = self.forwardable_headers(incoming)
        headers["x-api-key"] = self.key or ""
        headers["anthropic-version"] = config.anthropic_version
        headers["content-type"] = "application/json"
        return headers

    def new_stream_accumulator(self) -> StreamAccumulator:
        return _AnthropicStream()
