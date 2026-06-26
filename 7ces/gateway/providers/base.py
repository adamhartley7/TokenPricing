"""
Provider adapter interface. A provider knows how to talk to one upstream API:
  * where to send the request and how to authenticate (with the gateway's OWN key, never the
    client's — the real key never leaves the gateway's .env),
  * how to bound output (inject a default max_tokens so worst-case output cost is finite),
  * how to read the actual token usage back, from both a plain JSON response and an SSE stream.

Adding a provider = ~40 lines here + one pricing.json entry + one librechat.yaml endpoint.
"""
from __future__ import annotations

from typing import Any

# Hop-by-hop / auth headers we never forward upstream from the client.
_STRIP_REQUEST_HEADERS = {
    "host", "content-length", "connection", "authorization", "x-api-key",
    "accept-encoding", "anthropic-version",
}


class StreamAccumulator:
    """Collects token usage from a stream of parsed SSE `data:` objects."""

    def __init__(self) -> None:
        self.usage: dict | None = None

    def feed(self, data_obj: dict) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def result(self) -> dict | None:
        return self.usage


class Provider:
    name: str = "base"
    max_tokens_field: str = "max_tokens"

    def __init__(self, base_url: str, key: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.key = key

    # -- routing & auth -------------------------------------------------------
    def upstream_url(self, subpath: str) -> str:
        return f"{self.base_url}/{subpath.lstrip('/')}"

    def auth_headers(self, incoming: dict[str, str]) -> dict[str, str]:  # pragma: no cover
        raise NotImplementedError

    def forwardable_headers(self, incoming: dict[str, str]) -> dict[str, str]:
        """Pass through safe client headers (e.g. anthropic-beta) but never auth."""
        out = {}
        for k, v in incoming.items():
            if k.lower() in _STRIP_REQUEST_HEADERS:
                continue
            out[k] = v
        return out

    # -- request shaping ------------------------------------------------------
    def prepare(self, body: dict, default_max_tokens: int) -> tuple[dict, str, int, bool]:
        """
        Return (prepared_body, model, effective_max_tokens, is_stream).
        Injects a default max_tokens when absent so output is always bounded, and enables usage
        reporting on streamed responses.
        """
        b = dict(body)
        model = b.get("model")
        # Always end up with a positive int max_tokens. A missing, zero, NEGATIVE, or non-int value
        # is replaced with the default — a negative value would otherwise deflate the worst-case
        # estimate and defeat the cap (and upstreams reject non-ints). Write the clean value back.
        try:
            requested = int(b.get(self.max_tokens_field))
        except (TypeError, ValueError):
            requested = 0
        max_tokens = requested if requested > 0 else default_max_tokens
        b[self.max_tokens_field] = max_tokens
        is_stream = bool(b.get("stream", False))
        self._enable_stream_usage(b, is_stream)
        return b, model, max_tokens, is_stream

    def _enable_stream_usage(self, body: dict, is_stream: bool) -> None:
        """Default: nothing to do (overridden where the provider needs an opt-in)."""

    # -- usage extraction -----------------------------------------------------
    def usage_from_json(self, payload: dict) -> dict | None:
        return payload.get("usage") if isinstance(payload, dict) else None

    def new_stream_accumulator(self) -> StreamAccumulator:  # pragma: no cover
        raise NotImplementedError


def coerce_per_request_cap(headers: dict[str, str]) -> float | None:
    """Honor an optional `x-7Cs-cap` header (USD) as a per-request cap override."""
    for k, v in headers.items():
        if k.lower() == "x-7Cs-cap":
            try:
                val = float(v)
                return val if val > 0 else None
            except (TypeError, ValueError):
                return None
    return None
