"""DeepSeek adapter — OpenAI-compatible Chat Completions shape."""
from __future__ import annotations

from providers.base import Provider, StreamAccumulator


class _OpenAIStream(StreamAccumulator):
    """
    OpenAI/DeepSeek SSE: most chunks have `usage: null`; when `stream_options.include_usage` is set,
    the final chunk before `[DONE]` carries the full usage object. Keep the last non-null one.
    """

    def feed(self, data_obj: dict) -> None:
        u = data_obj.get("usage")
        if u:
            self.usage = dict(u)


class DeepSeekProvider(Provider):
    name = "deepseek"
    max_tokens_field = "max_tokens"

    def auth_headers(self, incoming: dict[str, str]) -> dict[str, str]:
        headers = self.forwardable_headers(incoming)
        headers["authorization"] = f"Bearer {self.key or ''}"
        headers["content-type"] = "application/json"
        return headers

    def _enable_stream_usage(self, body: dict, is_stream: bool) -> None:
        # Ask DeepSeek to include usage in the final streamed chunk so we can meter actual cost.
        if is_stream:
            opts = dict(body.get("stream_options") or {})
            opts["include_usage"] = True
            body["stream_options"] = opts

    def new_stream_accumulator(self) -> StreamAccumulator:
        return _OpenAIStream()
