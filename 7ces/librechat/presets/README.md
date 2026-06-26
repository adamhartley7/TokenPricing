# §5.1 controls in LibreChat — Presets

The brief's per-request Chat controls map onto LibreChat like this:

| §5.1 control | Where it lives in LibreChat |
|---|---|
| **Provider + model** | the endpoint + model dropdown (DeepSeek / Claude) |
| **Output length** | **Max Output Tokens** (Advanced Settings, or per-Preset) — also the gateway's output bound |
| **Depth / "time thinking"** | **reasoning effort** — for DeepSeek set `reasoning_effort` (non-thinking → `low`, thinking → `medium`, max → `high`); for Claude, effort is adaptive |
| **Output format** | the **system prompt** — paste one of the templates in this folder |
| **Spend cap** | enforced by the gateway (per-request / session / day). Tighten a single message with **Max Output Tokens**, or send the header `x-7Cs-cap: <usd>` |

## Make a Preset (once), then pick it per request

1. In LibreChat, open **Advanced Settings** (the sliders icon by the chat bar).
2. Choose the endpoint + model (e.g. **DeepSeek → deepseek-v4-flash**).
3. Set **Max Output Tokens** (your length cap) and, for DeepSeek, **reasoning_effort** (your depth).
4. Paste one of these templates into the **system prompt / custom instructions** box:
   - [`format-markdown.md`](format-markdown.md) — clean Markdown answer
   - [`format-html-artifact.md`](format-html-artifact.md) — one self-contained interactive `.html` file
   - [`format-produce-file.md`](format-produce-file.md) — produce a file / buildable output
5. Click **Save As Preset**, name it (e.g. `DeepSeek · HTML artifact · tight`), and it appears in the
   Presets menu to select per request.

Suggested preset tiers (model + max tokens encode a rough cost ceiling):
- `DeepSeek · tight` — deepseek-v4-flash, max 512, reasoning low
- `DeepSeek · deep` — deepseek-v4-pro, max 4096, reasoning high
- `Claude · scalpel` — claude-opus-4-8, max 2048 (used sparingly — it's the priciest)

> The gateway caps every call regardless of preset, so a misconfigured preset can't overspend.
