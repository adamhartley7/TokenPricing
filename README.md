# TokenPricing

Neutral, fully-sourced cost + strategy tool for a heavy coding-agent user (June 2026), covering
**Claude · DeepSeek · Gemini · OpenAI · Qwen · local (Ollama)** across three axes:
metered API vs flat subscription vs self-hosted.

**Live:** https://adamhartley7.github.io/TokenPricing/ — served via GitHub Pages from the
`claude/token-app-deepseek-cost-analysis-fvsql5` branch (root). Or open `index.html` locally.
(When you merge into `main`, repoint Pages at `main`.)

## What's here
- **`index.html`** — single-file app with four modes:
  - **Calculator** — enter your monthly input / output / cache-write / cache-read tokens (the four
    `ccusage` columns) and see live monthly cost for every metered model, with subscription prices and
    a local-electricity estimate as reference lines, plus the Sonnet/Opus subscription break-even.
  - **Explainer** — how tokens, caching, and subscription-vs-API break-even actually work.
  - **Local agents** — running models with Ollama: VRAM→model-size guide, tokens/sec, and a real
    electricity-based running-cost estimate.
  - **Setup & linking** — the safe usage-sync workflow and why API keys must never go in a public page.
- **[REPORT.md](./REPORT.md)** — the full written analysis: all-provider price table, break-even math,
  Claude Code↔DeepSeek routing, privacy/jurisdiction, OpenAI sub-vs-API, Qwen, and local agents. Every
  figure cited with an access date; unconfirmed figures flagged.
- **`sync-usage.ps1`** — local Windows script: runs `ccusage` and writes `usage.json` (local only).
- **`profile.local.example.json`** — schema for optional personalization.

## Personalize it (local only, never published)
1. `./sync-usage.ps1` → writes `usage.json` (your real usage; git-ignored).
2. Copy `profile.local.example.json` → `profile.local.json` and fill in your role / location / devices.

The page `fetch()`es both files at load and personalizes if present; if absent it shows generic
defaults. Both are git-ignored so the published page stays free of personal data.

> Cost estimates only; not financial advice. Many non-Claude prices are unverified (official pages
> blocked the fetch) — flagged in-app and in REPORT.md. Verify live prices before committing spend.
