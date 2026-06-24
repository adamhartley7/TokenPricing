# LLM Pricing & Routing: A Neutral Buyer's Guide (June 2026)

> Audience: a cost-conscious **heavy coding-agent (Claude Code) user** who wants the cheapest sound way to get high-quality agentic work done — and is willing to mix metered APIs, a flat subscription, and/or local models.
> Scope: pay-per-token APIs (Claude, DeepSeek, Gemini, **OpenAI**, **Qwen**) vs flat rate-limited subscriptions (**Claude Max 5x / 20x**, **ChatGPT Plus / Pro**) vs **running models locally with Ollama** (marginal token cost ~$0, but real hardware + electricity cost).
> All quantitative claims are cited inline with a source URL + access date. Figures marked **unconfirmed** could not be verified against the primary source on this run (see [Sources](#sources)). Recommendations are **not financial advice**.

---

## 1. Bottom line (neutral)

No single vendor wins on every axis, so the honest answer is a split. **DeepSeek has the clear raw-token cost advantage** — its V4 Flash tier is roughly an order of magnitude cheaper than the cheapest comparable Claude/Gemini tiers — **but it carries a real data-jurisdiction caveat**: DeepSeek's hosted API stores personal data on servers in the People's Republic of China, and multiple governments have restricted it on official devices. For an EU user handling proprietary code, that caveat matters. Meanwhile, **a flat Claude Max subscription is not comparable to a metered API**: at the volume an all-day agentic Claude Code user generates, the flat $100-$200/mo plan is almost always far cheaper per unit of work than paying Claude API rates for the same tokens — but it is rate-limited and (since 15 Jun 2026) headless/programmatic use bills separately at API rates. The pragmatic shape: **keep Claude Max for interactive native Claude Code work, add a cheap metered key (Gemini Flash-Lite/Flash favoured over DeepSeek for an EU user) for bulk/background/vision, and treat the Claude API as a scalpel, not a daily driver.** Detail and the break-even math follow.

---

## 2. Refreshed all-provider price table

All token figures are USD **per 1M tokens (MTok)**, shown as **input / output**. Subscriptions are flat monthly and rate-limited — they have *no* per-token price and are listed as such.

| Offering | Model / tier | Input / Output per 1M | Notes | Source |
|---|---|---|---|---|
| **DeepSeek API** (metered) | V4 Flash | **$0.14 / $0.28** | Cache-hit input ~$0.0028/1M (~98% off). 1M context. **Unconfirmed** (official page 403; aggregator fallback). | [docs][s-ds-price] (2026-06-24) |
| **DeepSeek API** (metered) | V4 Pro | **$0.435 / $0.87** | The 75% cut made **permanent after 2026-05-31** (corroborated across aggregators; official page 403). Cache-hit input ~$0.003625/1M. Original list was ~$1.74 / $3.48. | [docs][s-ds-price] (2026-06-24) |
| **Claude API** (metered) | Opus 4.8 | **$5 / $25** | Fast mode (Opus only) $10 / $50. Batch -50%. Cache read 0.1x input ($0.50); 5m cache write 1.25x ($6.25). | [pricing][s-claude-price] (2026-06-24) |
| **Claude API** (metered) | Sonnet 4.6 | **$3 / $15** | Batch -50% ($1.50 / $7.50). Cache read $0.30. | [pricing][s-claude-price] (2026-06-24) |
| **Claude API** (metered) | Haiku 4.5 | **$1 / $5** | Batch -50% ($0.50 / $2.50). Cache read $0.10. | [pricing][s-claude-price] (2026-06-24) |
| **Gemini API** (metered) | Gemini 3 Pro | **$2 / $12** (<=200k ctx); **$4 / $18** (>200k) | Batch -50%. Free tier exists but **trains on your data**. Native vision. **Unconfirmed** (official page 403; aggregators label it "3.1 Pro" — generation labelling inconsistent). | [pricing][s-gemini-price] (2026-06-24) |
| **Gemini API** (metered) | 3.5 Flash | **$1.50 / $9** | Batch -50%. **Unconfirmed** (aggregator fallback). | [pricing][s-gemini-price] (2026-06-24) |
| **Gemini API** (metered) | 3.1 Flash-Lite | **$0.25 / $1.50** | Cheapest Gemini with current-gen quality. **Unconfirmed**. | [pricing][s-gemini-price] (2026-06-24) |
| **Gemini API** (metered) | 2.5 Flash-Lite | **$0.10 / $0.40** | Older gen; cheapest listed. **Unconfirmed**. | [pricing][s-gemini-price] (2026-06-24) |
| **Claude Max 5x** (subscription) | flat, rate-limited | **flat $100/mo, rate-limited** | ~225 msgs / rolling 5h (approx). No per-token price. Anthropic does **not** publish exact token quotas. | [pricing][s-claude-price] (2026-06-24) |
| **Claude Max 20x** (subscription) | flat, rate-limited | **flat $200/mo, rate-limited** | ~900 msgs / rolling 5h (approx). No per-token price. Quotas not published. | [pricing][s-claude-price] (2026-06-24) |
| **OpenAI API** (metered) | GPT-5.5 (flagship) | **$5.00 / $30.00** | Cached input $0.50. Batch & Flex ~half rate; Priority ~2.5x. GPT-5.5-pro variant $30 / $180. **Unconfirmed** (all OpenAI pages 403; aggregator fallback). | [openai][s-oai] (2026-06-24) |
| **OpenAI API** (metered) | GPT-5.4 | **$2.50 / $15.00** | Cached input $0.25. Predecessor flagship, still in API. **Unconfirmed**. | [openai][s-oai] (2026-06-24) |
| **OpenAI API** (metered) | GPT-5.4 mini | **$0.75 / $4.50** | Cached input $0.075. No "GPT-5.5 mini" exists yet. **Unconfirmed**. | [openai][s-oai] (2026-06-24) |
| **OpenAI API** (metered) | GPT-5.4 nano | **$0.20 / $1.25** | Cached input $0.02. Cheapest current-gen OpenAI tier. **Unconfirmed**. | [openai][s-oai] (2026-06-24) |
| **OpenAI API** (metered) | GPT-5.3-codex (Codex CLI default) | **$1.75 / $14.00** | Cached input $0.175. Coding-agent model. **Unconfirmed**. | [openai][s-oai] (2026-06-24) |
| **ChatGPT Plus** (subscription) | flat, rate-limited | **flat $20/mo, rate-limited** | Includes GPT-5.5, Codex CLI/web/IDE (rolling 5h limits), Agent Mode, ~10 Deep Research/mo. No per-token price. **Unconfirmed**. | [openai][s-oai] (2026-06-24) |
| **ChatGPT Pro** (subscription) | flat, rate-limited | **flat $100/mo (5x) or $200/mo (20x)** | Pro 5x ($100): 5x Plus quotas, 50 Deep Research/mo. Pro 20x ($200): 20x quotas, 250 Deep Research/mo, GPT-5.4 1M-context. Codex CLI heavy-use tier. **Unconfirmed**. | [openai][s-oai] (2026-06-24) |
| **Qwen API** (metered) | qwen-flash (budget) | **~$0.05 / $0.40** (≤256k); rises to ~$0.25 / $2.00 on long input | Alibaba Model Studio, Singapore endpoint; tiered by input length. Batch -50%. New accounts: 1M+1M free tokens, 90 days. **Unconfirmed** (403; aggregator fallback; cross-source variance). | [qwen][s-qwen] (2026-06-24) |
| **Qwen API** (metered) | qwen-plus (mid) | **~$0.40 / $1.20** (cited as low as $0.26 / $0.78) | Climbs to ~$1.20 / $3.60 past 256k. **Unconfirmed**; figures vary across sources. | [qwen][s-qwen] (2026-06-24) |
| **Qwen API** (metered) | qwen-max / Qwen3.x-Max (flagship) | **~$2.50 / $7.50** list (promo ~$1.25 / $3.75; DashScope ~$1.20 / $6.00) | Maps to Qwen3.6/3.7 generations. **Unconfirmed**; wide cross-source variance. | [qwen][s-qwen] (2026-06-24) |
| **Local / Ollama** (self-host) | any open-weight (Qwen / DeepSeek / Llama / gpt-oss) | **~$0 marginal / token** | No per-token billing — only electricity + amortized hardware (see [section 11](#11-local-agents-with-ollama)). MIT/Apache-licensed weights. Quality/speed bounded by your VRAM. | [ollama][s-ollama], [hw][s-hw] (2026-06-24) |

> Additional Claude consumer tier for reference: **Pro $20/mo** (1x), rate-limited. ([pricing][s-claude-price], 2026-06-24)
> Additional ChatGPT tiers for reference: **Free $0**; **Go $8/mo**; **Business $25/user/mo** (annual) / $30 monthly, min 2 users, training-data exclusion by default; **Enterprise** custom. ([openai][s-oai], 2026-06-24, **unconfirmed**)
>
> Quality anchor (SWE-bench Verified, ~June 2026): **Opus 4.8 ~= 88.6%**, **DeepSeek V4 Pro ~= 80.6%** — cost is not the only axis. (seed figures; benchmark provenance not independently re-verified this run)

**Caveats on the table:** DeepSeek, Gemini, **OpenAI**, and **Qwen** official pricing pages all returned **HTTP 403** on this run; their figures come from WebSearch aggregators and are **not verified against the primary source**. The Gemini aggregators mixed generations (2.5 / 3.1 / 3.5). OpenAI's lineup has clearly advanced past the Jan-2026 knowledge cutoff (GPT-5.5 / 5.4 / 5.3-codex), and there is **no GPT-5.5 mini/nano yet** — the small tiers live in the GPT-5.4 family. Qwen figures show wide cross-source variance and the API aliases (`qwen-flash`/`plus`/`max`) now map to newer generations; **Qwen3.7 is closed/API-only, not open-weight** as of the access date. Only **Claude API** figures and the **Ollama mechanics + the local-hardware/electricity rules of thumb** are confirmed from primary/successfully-fetched sources. Treat all unconfirmed numbers as directional and re-verify before committing spend.

---

## 3. Subscription vs API isn't like-for-like

A flat **Claude Max** plan and a metered **API** are priced on different axes and cannot be compared per-token:

- **Claude Max is a flat fee with a rate limit, not a token meter.** You pay $100 (5x) or $200 (20x) per month and get a *capacity ceiling* — roughly **~225 (5x) / ~900 (20x) messages per rolling 5-hour window**, plus two weekly caps (one all-models, one Sonnet-only). The 5-hour limit was doubled on 6 May 2026. ([pricing][s-claude-price], 2026-06-24) Crucially, **Anthropic does not publish exact token quotas** for these plans — the only public anchors are the relative multipliers (Pro = 1x, Max = 5x / 20x). Any specific "X tokens/month" figure for a subscription would be invented; this report does not.
- **The API is pure metered usage.** You pay exactly $/MTok for what you send and receive, with no ceiling and no flat fee. Cost scales linearly and without bound.

**Where each wins:**

- **Light/occasional or bursty-but-capped usage -> API.** If you only run a few thousand tokens a day, metered billing costs cents and you avoid a $100-$200 commitment.
- **Heavy, sustained interactive usage -> subscription.** A full-time Claude Code user easily pushes tens of millions of tokens per day across long agentic transcripts (huge context re-reads, tool loops). At that volume the flat plan's effective per-token cost collapses far below API rates — you're buying a capped firehose for a fixed price. The crossover is quantified in [section 6](#6-break-even-math).
- **The catch (15 Jun 2026 change):** **programmatic / non-interactive usage** (Agent SDK, `claude -p`, GitHub Actions, scheduled/headless runs) **no longer draws from the flat subscription pool.** It draws from a **separate monthly credit pool billed at API rates** — **$20 (Pro) / $100 (Max 5x) / $200 (Max 20x)** of API-priced credit. **Interactive terminal use is unaffected.** ([pricing][s-claude-price], 2026-06-24, per seed change note) So the "flat plan beats API" logic holds for *interactive* work but **not** for headless agents past that credit allowance.

---

## 4. Running Claude Code on DeepSeek (Windows)

Claude Code can be pointed at DeepSeek's Anthropic-compatible endpoint. Two routes:

### A. Official: `ANTHROPIC_BASE_URL` env vars (PowerShell `$env:` syntax)

```powershell
$env:ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN = "<your DeepSeek API key>"   # from https://platform.deepseek.com/api_keys

# Model overrides (verbatim from the deepseek-ai docs mirror)
$env:ANTHROPIC_MODEL = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = "deepseek-v4-pro"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = "deepseek-v4-flash"
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
$env:CLAUDE_CODE_EFFORT_LEVEL = "max"

claude   # launch Claude Code as usual
```

Anthropic-name -> DeepSeek mapping (from DeepSeek docs): `claude-opus*` -> `deepseek-v4-pro`; `claude-haiku*` / `claude-sonnet*` -> `deepseek-v4-flash` (the mirror's env-var block routes Sonnet -> `deepseek-v4-pro` instead — **naming is version-dependent, verify the live docs**). ([DeepSeek Claude Code docs][s-ds-cc], 2026-06-24)

### B. Community: claude-code-router (`@musistudio/claude-code-router`)

A free, open-source local proxy (runs on `http://localhost:3456`) that multiplexes multiple providers.

```powershell
npm install -g @musistudio/claude-code-router
ccr code        # launches Claude Code routed through the proxy
# ccr ui   -> web config | ccr model -> model picker | ccr restart -> after config edits
```

It works by setting `ANTHROPIC_BASE_URL=http://localhost:3456` so Claude Code's calls hit the router, which rewrites/forwards to the configured provider. DeepSeek provider config lives in `~/.claude-code-router/config.json`; restart with `ccr restart` after edits. For CI set `NON_INTERACTIVE_MODE: true`. ([claude-code-router README][s-ccr], 2026-06-24)

### Honest reliability caveats

- **Tool-use reliability.** Claude Code leans heavily on tool calling. Non-Anthropic backends behind an Anthropic-compatible shim **may handle tool/function calls less reliably** than native Claude. The DeepSeek docs mirror did **not** publish an explicit tool-use-reliability guarantee or warning either way — so treat this as **untested in your workflow** and verify on real tasks before trusting it for parallel agentic loops. ([DeepSeek Claude Code docs][s-ds-cc], 2026-06-24)
- **claude-code-router is community/third-party**, not an Anthropic product. Several provider transformers are marked experimental and some features beta; it breaks if Claude Code's upstream API contract changes. ([claude-code-router README][s-ccr], 2026-06-24)
- **Model-name churn.** DeepSeek's model ids are version-dependent (`deepseek-v4-pro`/`-flash` now; older examples used `deepseek-chat`/`deepseek-reasoner`, which **deprecate 2026-07-24** and route to V4). Re-check the live docs. ([DeepSeek docs][s-ds-cc], 2026-06-24)

---

## 5. Privacy / jurisdiction (neutral, sourced)

This is the counterweight to DeepSeek's cost win. Stated plainly, no editorialising:

- **Hosted DeepSeek API -> data stored in the PRC.** DeepSeek's own Privacy Policy states personal information is stored on "secure servers located in the People's Republic of China," and the service is operated by Hangzhou DeepSeek Artificial Intelligence Co., Ltd. Collected data includes chat prompts, uploaded files, profile data, and device/network data. Because the data sits in China, it is subject to PRC cybersecurity/national-security laws that can compel disclosure to authorities. **Note: the primary privacy-policy page returned HTTP 403 this run; wording is corroborated by the dated CDN filename and multiple secondary sources — treat as unconfirmed against the source.** ([DeepSeek Privacy Policy + reporting][s-ds-privacy], 2026-06-24)
- **Government restrictions on official devices** (mostly late Jan-Feb 2025; current standing not re-verified): **Italy** (Garante limited processing, app pulled from stores), **Australia** (removed from government systems), **Taiwan** (government departments blocked), **South Korea** (banned on some agency devices), and the **US** (Navy, NASA, Pentagon, Dept. of Commerce restrictions; "No DeepSeek on Government Devices Act" HR 1121 introduced; Texas banned it on state systems). ([reporting][s-ds-privacy], 2026-06-24)
- **Open-weight / self-host / Western-hosted alternatives soften the caveat.** DeepSeek publishes open-weight releases on Hugging Face under the **MIT License** (commercial use, modification, redistribution allowed), self-hostable via vLLM / SGLang / LMDeploy, and served by Western providers (OpenRouter, Fireworks, Together, Perplexity). Perplexity self-hosts DeepSeek R1 in US data centres and states data does not go to China. **A self-hosted or Western-hosted deployment does not transmit your data to DeepSeek's PRC servers** — this is the route to use DeepSeek with sensitive/proprietary data. ([open-weight/hosting sources][s-ds-privacy], 2026-06-24)
- **fp8 quantisation quality note.** Many serverless hosts quantise DeepSeek activations to fp8 to cut cost, which can move output away from the reference bf16 weights and degrade quality; quality varies by provider. Some hosts advertise non-quantised (bf16) serving as a differentiator. DeepSeek models were natively trained for FP8 (reported <0.25% relative loss vs bf16), so a *well-implemented* fp8 path can be near-lossless — but **provider implementation quality varies**, so pick the host deliberately. ([hosting/vendor sources][s-ds-privacy], 2026-06-24)
- **Gemini free tier** also has a privacy hook: it **trains on your data** and is not appropriate for sensitive/proprietary input — use a paid (non-training) tier for those. ([pricing][s-gemini-price], 2026-06-24)

---

## 6. Break-even math

**Question:** at what monthly token volume does flat **Claude Max 20x ($200/mo)** beat paying **Claude API** rates for the same tokens? (Interactive use only — the section 3 programmatic-pool change is separate.)

**Assumptions:** 80/20 input/output blend. Blended price per 1M tokens:

```
blended $/1M = 0.8 * input + 0.2 * output
```

| Model | input / output | Blended $/1M = 0.8*in + 0.2*out |
|---|---|---|
| Sonnet 4.6 | $3 / $15 | 0.8*3 + 0.2*15 = **$5.40 / 1M** |
| Opus 4.8 | $5 / $25 | 0.8*5 + 0.2*25 = **$9.00 / 1M** |

**Crossover formula** (tokens where API spend = $200 flat):

```
breakeven_tokens = $200 / blended_$_per_token
                 = $200 / (blended_$_per_1M / 1,000,000)
```

| Model | Crossover (tokens/mo where API spend = $200) |
|---|---|
| **Sonnet 4.6** | 200 / 5.40 * 1M ~= **37.0M tokens/mo** |
| **Opus 4.8** | 200 / 9.00 * 1M ~= **22.2M tokens/mo** |

**Reading it:** if your *interactive* monthly usage exceeds **~37M blended tokens on Sonnet** or **~22M on Opus**, the flat **Max 20x** plan is cheaper than metered Claude API — and a heavy all-day Claude Code user blows past these in days, not months (a single long agentic session can re-read large contexts and run into millions of tokens). Below those volumes, metered API is cheaper. (For Max 5x at $100/mo, halve the crossovers: ~18.5M Sonnet / ~11.1M Opus.)

**Where Gemini and DeepSeek sit:** both are *far* below these crossovers — i.e., for the same token volume their metered bill is a small fraction of $200, so the subscription-vs-API crossover argument barely applies to them. Using the same 80/20 blend: DeepSeek V4 Flash ~= **$0.168/1M** (a hypothetical 37M tokens ~= **$6.2**); Gemini 3.1 Flash-Lite ~= **$0.50/1M** (37M ~= **$18.5**); Gemini 3 Pro <=200k ~= **$4.00/1M** (37M ~= **$148**). These are cheap-bulk tiers, not subscription substitutes for sustained Claude-quality agentic work. (DeepSeek/Gemini per-1M figures **unconfirmed** — see table.)

---

## 7. OpenAI: subscription vs API

OpenAI presents the same fork as Claude — a flat **ChatGPT** subscription vs a metered **API** — plus a Codex coding-agent CLI that can bill *either* way. All OpenAI figures here are **unconfirmed** (every OpenAI pricing page returned HTTP 403 this run; numbers are from aggregators citing OpenAI). ([openai][s-oai], 2026-06-24)

- **ChatGPT subscription (flat, rate-limited):** **Free $0 · Go $8 · Plus $20 · Pro $100 (5x) / $200 (20x) · Business $25–30/user · Enterprise custom.** Plus ($20) bundles **GPT-5.5**, the **Codex CLI/web/IDE** coding agent (rolling 5-hour task/review limits), Agent Mode, and ~10 Deep Research/mo. Pro 5x ($100) is OpenAI's recommended tier for *heavy* Codex use; Pro 20x ($200) adds GPT-5.4 1M-context access and 250 Deep Research/mo. As with Claude Max, **OpenAI does not publish exact token quotas** for these tiers — only relative multipliers — so don't infer a token budget from the price.
- **API (pure metered):** flagship **GPT-5.5 $5 / $30** per 1M (cached input $0.50); **GPT-5.4 $2.50 / $15**; small tiers in the 5.4 family (**mini $0.75 / $4.50**, **nano $0.20 / $1.25**); coding model **GPT-5.3-codex $1.75 / $14**. Batch & Flex run ~half rate; Priority ~2.5x. No ceiling, no flat fee.
- **Codex CLI billing (two ways):** (1) **bundled with a ChatGPT subscription** — Plus $20 includes Codex CLI/web/IDE with rolling 5-hour limits; Pro 5x ($100) recommended for heavy dev use; or (2) **sign in with an API key** and pay standard per-token rates to your Platform account (e.g. GPT-5.3-codex $1.75 / $0.175 / $14 per 1M). On **2026-04-02** OpenAI switched Codex from per-message to token-based credit pricing. Typical heavy-dev usage is cited at ~$100–200/dev/month.
- **How it maps to the Claude decision:** the break-even logic in [section 6](#6-break-even-math) is identical in shape. If your *interactive* Codex/ChatGPT usage is heavy and sustained, the flat $20/$100/$200 plan almost always beats metering GPT-5.5 at $5/$30 per 1M; if usage is light/bursty, the API is cheaper. **Note:** there is **no GPT-5.5 mini/nano** yet — the cheap small tiers are GPT-5.4 mini/nano.

---

## 8. Qwen (API + open-weight local)

Alibaba's **Qwen** family is notable for being both a cheap hosted API *and* a strong **open-weight** line you can run locally for ~$0/token. All Qwen figures are **unconfirmed** (primary pages 403; aggregator/secondary fallback; wide cross-source variance). ([qwen][s-qwen], 2026-06-24)

- **Open-weight local (Apache 2.0 — unrestricted commercial use/modification/redistribution):** the newest open-weight flagship as of the access date is **Qwen3.6-27B** (dense, Apr 2026) alongside a **Qwen3.6-35B-A3B** MoE (~3B active), 262k context, text+image+video input. Earlier open lines (Qwen3.5, Qwen3) span 0.6B → 235B-A22B. **Qwen3.7 (Max/Plus) is closed / API-only — not open-weight yet.** So for local use the practical flagship is **Qwen3.6-27B** (~17 GB at Q4 per Ollama), which fits the same VRAM tiers as a 32B-class model (see [section 11](#11-local-agents-with-ollama)).
- **Hosted API (Alibaba Cloud Model Studio / DashScope, Singapore endpoint, per 1M, tiered by input length):** **qwen-flash ~$0.05 / $0.40** (rising to ~$0.25 / $2.00 on long inputs); **qwen-plus ~$0.40 / $1.20** (cited as low as $0.26 / $0.78); **qwen-max ~$2.50 / $7.50** list (promo ~$1.25 / $3.75; DashScope direct ~$1.20 / $6.00). Batch -50%. New Singapore-region accounts get **1M input + 1M output tokens free for 90 days**. The Mainland (Beijing) endpoint is ~60–70% cheaper but has **no free quota and stores data in China** (jurisdiction caveat similar to DeepSeek's hosted API).
- **Also available via OpenRouter** (Western-hosted; e.g. Qwen3-Max ~$0.78 / $3.90, Qwen3-235B-A22B ~$0.455 / $1.82, plus a free `qwen3-235b-a22b:free` variant) and **Ollama** for local.
- **Why it matters for a coding-agent user:** Qwen-Coder variants are commonly run locally behind Ollama's OpenAI-compatible endpoint to back a coding agent at ~$0 marginal cost. The trade vs Claude/GPT is quality and tool-use reliability — verify on your real tasks.

---

## 9. Running Claude Code on alternative APIs

(See [section 4](#4-running-claude-code-on-deepseek-windows) for the DeepSeek-specific walkthrough and the `claude-code-router` proxy, which also fronts OpenAI/Gemini/Qwen/local providers.)

---

## 11. Local agents with Ollama

This is the third option alongside metered APIs and flat subscriptions: **run an open-weight model on your own hardware.** The per-token billing is **~$0** — you pay only electricity and amortized hardware. The catch is that model quality and speed are bounded by your VRAM/RAM. (Ollama mechanics below are **confirmed** via the official GitHub README + reputable secondary docs; the hardware rules of thumb are **confirmed** from community llama.cpp benchmarks; the electricity figures are **unconfirmed** — Irish primary pages 403'd.)

### 11.1 How Ollama works

**Ollama** is a free, open-source (MIT) tool that runs LLMs locally. It wraps the **llama.cpp** inference engine behind a one-line install and a simple CLI: `ollama pull <model>` then `ollama run <model>`. Models are stored/executed as **quantized GGUF** files. ([ollama][s-ollama], 2026-06-24)

- **OpenAI-compatible local endpoint:** Ollama serves a REST API on **port 11434**, including an OpenAI-compatible surface at **`http://localhost:11434/v1`** (`/chat/completions`, `/completions`, `/embeddings`) with streaming, tool calling, and structured JSON. **Any tool that speaks the OpenAI API — VS Code extensions, Cursor, other coding agents — can be pointed at `http://localhost:11434/v1`** to use a local model as a drop-in cloud substitute. ([ollama][s-ollama], 2026-06-24)
- **Commonly run models:** Llama, **Qwen / Qwen3-Coder**, **DeepSeek-R1** (671B MoE plus smaller 1.5b–70b distillations), and OpenAI's open-weight **gpt-oss** (e.g. `gpt-oss:20b`, ~16 GB). ([ollama][s-ollama], 2026-06-24)
- **Quantization:** default is **Q4_K_M** (4-bit) — an optimal size/quality balance for most users; Q5/Q6/Q8 trade more memory for precision. ([ollama][s-ollama], 2026-06-24)
- **Marginal token cost ~$0:** inference runs entirely on local hardware with no per-token billing — only electricity and up-front/amortized hardware apply. ([ollama][s-ollama], 2026-06-24)

### 11.2 VRAM → model-size guide

Rule of thumb: **VRAM_GB ≈ params_billions × bytes_per_param × 1.2**, where bytes_per_param ≈ **0.5** (Q4_K_M), **1.0** (Q8), **2.0** (FP16). Add ~1–4 GB for long context (32k+) due to KV cache. ([hw][s-hw], 2026-06-24)

| Model size | Q4_K_M (most common) | Q8 | Practical fit |
|---|---|---|---|
| 7–8B | ~5–7 GB | ~8–10 GB | 8 GB GPU runs 7–8B Q4 comfortably |
| 13–14B | ~10–12 GB | ~15–17 GB | 12 GB → 13–14B Q4; 16 GB → 13–14B Q8 |
| 32–34B (incl. Qwen3.6-27B) | ~21–23 GB | ~35–38 GB | **24 GB (RTX 3090/4090) → 32–34B Q4 well** |
| 70B | ~40–46 GB | ~72–80 GB | needs **48 GB / 2×24 GB**; 24 GB only with slow CPU offload |

**GPU/VRAM tiers:** 8 GB → 7–8B Q4; 12 GB → ~13–14B Q4; 16 GB → 13–14B Q8 or 22–32B Q4 (tight); **24 GB → 32–34B Q4 comfortably**; 48 GB / 2×24 GB → 70B Q4. **Apple Silicon** (unified memory, ~67–75% allocatable to GPU): 16 GB → 7–8B; 32 GB → up to ~32B Q4; 64 GB → 70B Q4 usable. **Old Intel Macs are CPU-only and not recommended** (a 2019 16 GB MBP runs 7B Q4 at only ~3–5 tok/s). **Thin-and-light laptops** (Core Ultra NPU / Xe iGPU): realistic ceiling ~7–8B Q4 at single-to-low-double-digit tok/s; **32B+ and 70B are not feasible**. ([hw][s-hw], 2026-06-24)

### 11.3 Tokens/sec expectations

Generation speed for an 8B model at Q4_K_M (llama.cpp, community benchmarks): **RTX 4090 ~128 tok/s · RTX 3090 ~112 tok/s**. Apple **M3 Max 64 GB**: 8B ~50.7 tok/s, 70B ~7.5 tok/s; **M2 Ultra 192 GB**: 8B ~76.3 tok/s, 70B ~12.1 tok/s. Older Pascal **GTX 1070/1080 8 GB**: 7B Q4 ~25–30 tok/s (and they thermal-throttle 20–40% under sustained load). Intel NPU (Core Ultra): ~8–12 tok/s on 8B INT4 at very low power. ([hw][s-hw], 2026-06-24) Note these are *generation* speeds; prompt-processing (prefill) differs, and big-context coding-agent runs are heavier than a single chat turn.

### 11.4 Worked running-cost example (Irish electricity + GPU watts)

This converts the "~$0/token" claim into a real running cost: **electricity + amortized hardware.** All inputs are **unconfirmed** point estimates (ranges given); treat as illustrative.

**Inputs** ([elec][s-elec], 2026-06-24): Irish residential electricity ≈ **€0.35/kWh** (range €0.30–0.42). A single-consumer-GPU desktop draws ≈ **300 W total system** under sustained inference (GPU 150–250 W + ~60–100 W rest). A thin-and-light laptop ≈ **35 W** under load. (Inference is bursty, so sustained-load watts *overstate* real interactive average use.)

**Electricity per hour of sustained load:**

- Desktop: 300 W × 1 h = 0.30 kWh × €0.35 = **≈ €0.105/hour** (~10.5 c/hr).
- Laptop: 35 W × 1 h = 0.035 kWh × €0.35 = **≈ €0.012/hour** (~1.2 c/hr).

**Electricity per 1M tokens** (illustrative, using the section 11.3 speeds):

- Desktop @ RTX 4090, 8B Q4 ~128 tok/s → 1M tokens ≈ 7,813 s ≈ **2.17 h** → ≈ **€0.23 / 1M tokens** of electricity.
- Even at a pessimistic 30 tok/s (older GPU / bigger model), 1M tokens ≈ 9.26 h → ≈ **€0.97 / 1M**.

So purely on electricity, local generation is **~€0.2–1.0 per 1M output tokens** — well below most metered output prices (e.g. Claude Sonnet $15/1M, GPT-5.5 $30/1M, even Gemini Flash-Lite $0.40–1.50/1M is comparable). **Caveat:** this counts *generation only*; a coding agent's heavy prompt-prefill and the slower speed of larger/higher-quality models push the real number up.

**Amortized hardware** (the part that makes "free" not free): a GPU capable of useful local coding work (e.g. a 24 GB RTX 3090/4090-class card for 32B Q4) is a significant up-front cost. Spread over, say, 24–36 months it adds a fixed monthly amount **regardless of token volume**. The honest framing: **local is cheapest per token at very high sustained volume, where the amortized hardware divides across many tokens; it is poor value at low volume**, where a metered API or a flat subscription you already own wins. Local also can't match flagship cloud quality (SWE-bench: Opus 4.8 ~88.6% vs the best you'll run on 24 GB), and tool-use reliability for agentic loops must be verified on your tasks.

---

## 12. Why you can't put API keys in a public page

A recurring temptation is to "link your account" or paste an API key into a static site so the page can show live usage or call a model directly. **Don't.** This is a confirmed security rule, not an opinion. ([keysec][s-keysec], 2026-06-24)

- **You cannot connect a Claude / Gemini / OpenAI *account* to a static page.** Those are authenticated, server-side relationships; there is no safe client-side hook that exposes your subscription usage to arbitrary JavaScript on a public page.
- **Any API key placed in client-side code on a public site is exposed.** Google's Gemini API docs state verbatim: *"Do not hardcode API keys directly in web or mobile apps. Keys compiled in client-side code can be extracted by users,"* and *"To secure client-side apps, run a backend proxy server to make the actual API calls."* OWASP's Secrets Management guidance and OpenAI's API-key-safety guidance agree: secrets must live only on a server, never in browser/static code — anyone can open *Inspect Element* and read the key. ([keysec][s-keysec], 2026-06-24)
- **The safe auto-update pattern = a local sync script, not a key in the page.** This repo's [`sync-usage.ps1`](./sync-usage.ps1) runs **`npx ccusage@latest monthly --json`** locally, parses the latest month, and writes **`usage.json`** to disk. The page then *optionally* `fetch()`es `usage.json` (and `profile.local.json`) from the same directory inside a `try/catch`, so a 404 silently degrades to neutral defaults. **Both files are git-ignored and never published** — no secret ever leaves your machine, and nothing is transmitted anywhere. If you ever genuinely need a client app to call a paid API, put the key behind your own backend proxy; never in the page.

---

## 13. How to decide (neutral)

> **Not financial advice.** Directional guidance based on the figures above; most non-Claude numbers are **unconfirmed** (403 on primary pages). Re-verify before committing spend.

The decision is really about **where your work sits on the volume curve**, plus jurisdiction and quality constraints:

1. **Pick the axis first — flat vs metered vs local.**
   - **Flat subscription wins for heavy, sustained *interactive* coding-agent use.** The break-even math ([section 6](#6-break-even-math)) shows the crossover at **~37M blended tokens/mo (Sonnet)** or **~22M (Opus)** vs $200 flat Claude Max — and a full-day Claude Code user blows past that in days. Generic rule: **if your monthly API-equivalent spend would run to several hundred dollars on a flat plan, the subscription wins decisively.** The same shape applies to ChatGPT Plus/Pro for Codex users ([section 7](#7-openai-subscription-vs-api)). **Start at the smaller tier (Max 5x / Plus) and step up only when you consistently hit the rate-limit caps** — don't pre-pay for headroom.
   - **Metered API wins for light, bursty, or specialized work** — bulk/background jobs (Batch -50%), vision, very large context, or spillover past a subscription's caps. Below the crossover, metering costs cents.
   - **Local (Ollama) wins on marginal cost at very high sustained volume**, once amortized hardware divides across enough tokens ([section 11](#11-local-agents-with-ollama)) — and for privacy, since nothing leaves your machine. It loses on flagship quality and on low-volume value.
2. **Layer a cheap metered key under whatever subscription you run**, for the things a flat plan does poorly: cheap bulk (Gemini Flash-Lite / Qwen-flash / DeepSeek V4 Flash), vision, or huge context. Keep the flagship API (Claude/OpenAI) as a *scalpel* for high-value Batch jobs, not a daily driver.
3. **Respect jurisdiction for sensitive/proprietary code.** Hosted **DeepSeek** and **Qwen Mainland** endpoints store data in the PRC ([section 5](#5-privacy--jurisdiction-neutral-sourced)); prefer Western-hosted, self-hosted (MIT/Apache open weights), or local for anything sensitive. **Gemini's free tier trains on your data** — use a paid tier for sensitive input.
4. **Mind the 15 Jun 2026 programmatic-pool change.** Headless/scheduled Claude use (Agent SDK, `claude -p`, GitHub Actions) draws from a **separate API-priced credit pool** ($20/$100/$200), **not** your flat interactive allowance. Budget for it, or route headless/background jobs to a cheap metered key or a local model instead of burning flagship credit.
5. **Never put an API key in a public page** ([section 12](#12-why-you-cant-put-api-keys-in-a-public-page)). Use the local `sync-usage.ps1` → `usage.json` pattern for auto-updating usage; a backend proxy if you ever need client-side API calls.

---

## Sources

All accessed **2026-06-24**. Items marked **(unconfirmed)** could not be verified against the primary source on this run (HTTP 403 or proxy denial); figures are from search-aggregator fallback and should be re-verified.

- **[s-claude-price]** Anthropic / Claude Platform Docs — Pricing (confirmed): <https://platform.claude.com/docs/en/about-claude/pricing>
- **[s-ds-price]** DeepSeek API Docs — Models & Pricing **(unconfirmed; 403, aggregator fallback)**: <https://api-docs.deepseek.com/quick_start/pricing>
- **[s-gemini-price]** Google Gemini API Pricing **(unconfirmed; 403, aggregator fallback)**: <https://ai.google.dev/gemini-api/docs/pricing>
- **[s-ds-cc]** DeepSeek API Docs — Claude Code integration **(unconfirmed; 403, official GitHub mirror used)**: <https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code> (mirror: <https://github.com/deepseek-ai/awesome-deepseek-agent/blob/main/docs/claude_code.md>)
- **[s-ccr]** claude-code-router (musistudio, community/unofficial) (confirmed): <https://github.com/musistudio/claude-code-router>
- **[s-ds-privacy]** DeepSeek Privacy Policy + government-restriction reporting + open-weight/hosting sources **(unconfirmed; primary 403, secondary corroboration)**: <https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy-2025-02-14.html>
- **[s-oai]** OpenAI API + ChatGPT pricing **(unconfirmed; all OpenAI pages 403; aggregator fallback citing OpenAI; lineup post knowledge-cutoff)**: <https://openai.com/api/pricing/>
- **[s-qwen]** Alibaba Qwen / Model Studio (DashScope) pricing + open-weight models **(unconfirmed; 403; aggregator/secondary; wide cross-source variance)**: <https://www.alibabacloud.com/help/en/model-studio/models>
- **[s-ollama]** Ollama mechanics + OpenAI-compatible local endpoint **(confirmed via official GitHub README + docs)**: <https://github.com/ollama/ollama> · <https://docs.ollama.com/api/openai-compatibility>
- **[s-hw]** Local-hardware VRAM rules of thumb + tokens/sec **(confirmed; llama.cpp community benchmarks + reputable secondary docs)**: <https://github.com/ggml-org/llama.cpp/discussions>
- **[s-elec]** Irish residential electricity price + device power draw **(unconfirmed; Irish primary pages 403; point estimate)**: <https://www.seai.ie/data-and-insights/seai-statistics/key-statistics/prices>
- **[s-keysec]** API-key security (no secrets in client-side/public code; use a backend proxy) **(confirmed)**: <https://ai.google.dev/gemini-api/docs/api-key> · <https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html> · <https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety>

[s-claude-price]: https://platform.claude.com/docs/en/about-claude/pricing
[s-ds-price]: https://api-docs.deepseek.com/quick_start/pricing
[s-gemini-price]: https://ai.google.dev/gemini-api/docs/pricing
[s-ds-cc]: https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code
[s-ccr]: https://github.com/musistudio/claude-code-router
[s-oai]: https://openai.com/api/pricing/
[s-qwen]: https://www.alibabacloud.com/help/en/model-studio/models
[s-ollama]: https://github.com/ollama/ollama
[s-hw]: https://github.com/ggml-org/llama.cpp/discussions
[s-elec]: https://www.seai.ie/data-and-insights/seai-statistics/key-statistics/prices
[s-keysec]: https://ai.google.dev/gemini-api/docs/api-key
[s-ds-privacy]: https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy-2025-02-14.html
