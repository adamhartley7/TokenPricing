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
- **`glm.ps1`** / **`deepseek.ps1`** — local Windows launchers: open a Claude Code session routed to
  GLM 5.2 (Z.ai) or DeepSeek V4 Pro so that work runs off your Claude weekly limit. Cached keys
  (`.glm-key` / `.deepseek-key`) are git-ignored. Run `./glm.ps1`; close the window to return to Claude.
- **`glm-overnight.ps1`** — long-run launcher: routes to GLM and keeps the PC awake until the session
  ends (restoring normal sleep on exit). Asks permissions by default; add **`-Unattended`** for true
  hands-off overnight work (skips Claude Code's permission prompts). `cd` into the target project first.
  Use `-Unattended` only in a git repo — see ADVANCED-SETUP §6.
- **`deepseek-overnight.ps1`** — same as `glm-overnight.ps1` but routed to **DeepSeek V4 Pro** (the
  cheapest metered overflow option). Reuses `.deepseek-key`. DeepSeek is an unofficial Claude Code route,
  so for delicate unattended runs prefer `glm-overnight.ps1`.
- **`claudelens.ps1`** — local Windows launcher: open [ClaudeLens](https://github.com/giulio333/ClaudeLens)
  (a desktop browser for your `~/.claude/` sessions, memory, skills and agents) routed to GLM 5.2, so its
  terminal and in-app chat also run off your Claude weekly limit. Reuses the same `.glm-key`. See ADVANCED-SETUP §8.
- **[ADVANCED-SETUP.md](./ADVANCED-SETUP.md)** — offload to GLM/DeepSeek, add a search + memory MCP server,
  import your Claude history for RAG, run the Opus-plans/cheap-workers orchestrator pattern, and fork
  LibreChat into your own modifiable chat/Cowork-style app.
- **`.claude/agents/`** — ready-made orchestrator-worker subagents (`bulk-implementer`, `researcher`,
  `test-writer` workers + an Opus `final-reviewer` quality gate).
- **`claude-code-router/config.example.json`** — route worker/background traffic to GLM, keep Opus as orchestrator.
- **`import-claude-export.py`** — turn your Anthropic data-export zip into clean Markdown for a memory/RAG store
  (local-only output; git-ignored).
- **`profile.local.example.json`** — schema for optional personalization.

## Personalize it (local only, never published)
1. `./sync-usage.ps1` → writes `usage.json` (your real usage; git-ignored).
2. Copy `profile.local.example.json` → `profile.local.json` and fill in your role / location / devices.

The page `fetch()`es both files at load and personalizes if present; if absent it shows generic
defaults. Both are git-ignored so the published page stays free of personal data.

> Cost estimates only; not financial advice. Many non-Claude prices are unverified (official pages
> blocked the fetch) — flagged in-app and in REPORT.md. Verify live prices before committing spend.
