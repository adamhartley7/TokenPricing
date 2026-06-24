# LLM Pricing & Routing: A Neutral Buyer's Guide (June 2026)

> Audience: a heavy Claude Code user on Windows, EU (Ireland), running parallel agentic loops, who also wants cheap bulk/background and vision work.
> Scope: pay-per-token APIs (DeepSeek, Claude, Gemini) vs flat rate-limited Claude consumer subscriptions (Max 5x / 20x).
> All quantitative claims are cited inline with a source URL + access date. Figures marked **unconfirmed** could not be verified against the primary source on this run (see [Sources](#sources)).

---

## 1. Bottom line (neutral)

No single vendor wins on every axis, so the honest answer is a split. **DeepSeek has the clear raw-token cost advantage** — its V4 Flash tier is roughly an order of magnitude cheaper than the cheapest comparable Claude/Gemini tiers — **but it carries a real data-jurisdiction caveat**: DeepSeek's hosted API stores personal data on servers in the People's Republic of China, and multiple governments have restricted it on official devices. For an EU user handling proprietary code, that caveat matters. Meanwhile, **a flat Claude Max subscription is not comparable to a metered API**: at the volume an all-day agentic Claude Code user generates, the flat $100-$200/mo plan is almost always far cheaper per unit of work than paying Claude API rates for the same tokens — but it is rate-limited and (since 15 Jun 2026) headless/programmatic use bills separately at API rates. The pragmatic shape: **keep Claude Max for interactive native Claude Code work, add a cheap metered key (Gemini Flash-Lite/Flash favoured over DeepSeek for an EU user) for bulk/background/vision, and treat the Claude API as a scalpel, not a daily driver.** Detail and the break-even math follow.

---

## 2. Refreshed 5-way price table

All token figures are USD **per 1M tokens (MTok)**, shown as **input / output**. Subscriptions are flat monthly and rate-limited — they have *no* per-token price and are listed as such.

| Offering | Model / tier | Input / Output per 1M | Notes | Source |
|---|---|---|---|---|
| **DeepSeek API** (metered) | V4 Flash | **$0.14 / $0.28** | Cache-hit input ~$0.0028/1M (~98% off). 1M context. **Unconfirmed** (official page 403; aggregator fallback). | [docs][s-ds-price] (2026-06-24) |
| **DeepSeek API** (metered) | V4 Pro | **$0.435 / $0.87** | Post-promo "standard" rate after 2026-05-31; cache-hit input ~$0.003625/1M. **Unconfirmed** whether now permanent. Pre-promo was ~$1.74 / $3.48. | [docs][s-ds-price] (2026-06-24) |
| **Claude API** (metered) | Opus 4.8 | **$5 / $25** | Fast mode (Opus only) $10 / $50. Batch -50%. Cache read 0.1x input ($0.50); 5m cache write 1.25x ($6.25). | [pricing][s-claude-price] (2026-06-24) |
| **Claude API** (metered) | Sonnet 4.6 | **$3 / $15** | Batch -50% ($1.50 / $7.50). Cache read $0.30. | [pricing][s-claude-price] (2026-06-24) |
| **Claude API** (metered) | Haiku 4.5 | **$1 / $5** | Batch -50% ($0.50 / $2.50). Cache read $0.10. | [pricing][s-claude-price] (2026-06-24) |
| **Gemini API** (metered) | Gemini 3 Pro | **$2 / $12** (<=200k ctx); **$4 / $18** (>200k) | Batch -50%. Free tier exists but **trains on your data**. Native vision. **Unconfirmed** (official page 403; aggregators label it "3.1 Pro" — generation labelling inconsistent). | [pricing][s-gemini-price] (2026-06-24) |
| **Gemini API** (metered) | 3.5 Flash | **$1.50 / $9** | Batch -50%. **Unconfirmed** (aggregator fallback). | [pricing][s-gemini-price] (2026-06-24) |
| **Gemini API** (metered) | 3.1 Flash-Lite | **$0.25 / $1.50** | Cheapest Gemini with current-gen quality. **Unconfirmed**. | [pricing][s-gemini-price] (2026-06-24) |
| **Gemini API** (metered) | 2.5 Flash-Lite | **$0.10 / $0.40** | Older gen; cheapest listed. **Unconfirmed**. | [pricing][s-gemini-price] (2026-06-24) |
| **Claude Max 5x** (subscription) | flat, rate-limited | **flat $100/mo, rate-limited** | ~225 msgs / rolling 5h (approx). No per-token price. Anthropic does **not** publish exact token quotas. | [pricing][s-claude-price] (2026-06-24) |
| **Claude Max 20x** (subscription) | flat, rate-limited | **flat $200/mo, rate-limited** | ~900 msgs / rolling 5h (approx). No per-token price. Quotas not published. | [pricing][s-claude-price] (2026-06-24) |

> Additional Claude consumer tier for reference: **Pro $20/mo** (1x), rate-limited. ([pricing][s-claude-price], 2026-06-24)
>
> Quality anchor (SWE-bench Verified, ~June 2026): **Opus 4.8 ~= 88.6%**, **DeepSeek V4 Pro Max ~= 80.6%** — cost is not the only axis. (seed figures; benchmark provenance not independently re-verified this run)

**Caveats on the table:** DeepSeek and Gemini official pricing pages both returned **HTTP 403** on this run; their figures come from WebSearch aggregators and are **not verified against the primary source**. The Gemini aggregators mixed generations (2.5 / 3.1 / 3.5), so it is unclear which is "current." Claude API figures and the claude-code-router config are **confirmed** from primary sources. Treat all unconfirmed numbers as directional and re-verify before committing spend.

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

## 7. Recommendation for this owner

> **Not financial advice.** Directional guidance based on the figures above; several DeepSeek/Gemini numbers are unconfirmed (403 on primary pages). Re-verify before committing spend.

1. **Keep Claude Max as your native Claude Code driver.** For sustained interactive agentic work, the flat plan is far cheaper than API at your volume ([section 6](#6-break-even-math)) and gives you native Opus/Sonnet quality and reliable tool use. **Start at 5x ($100/mo); move to 20x ($200/mo) only once you're consistently hitting the 5-hour/weekly caps** — don't pre-pay for headroom you aren't using.
2. **Add one cheap metered key for bulk / background / vision — favour Gemini over DeepSeek for you specifically.** As an **EU (Ireland)** user, Gemini Flash-Lite / Flash is the better default for non-sensitive bulk work: **Western jurisdiction, native vision, large context, and a free tier** (paid tier for anything sensitive, since the free tier trains on your data). Gemini 3.1 Flash-Lite (~$0.25/$1.50) or 2.5 Flash-Lite (~$0.10/$0.40) for cheap bulk; 3.5 Flash or 3 Pro when you need more capability or >200k context.
3. **If you do use DeepSeek, do it Western-hosted or self-hosted when personal/proprietary data is involved** — the hosted PRC API stores data in China ([section 5](#5-privacy--jurisdiction-neutral-sourced)). Self-host (MIT-licensed weights via vLLM/SGLang) or use a Western provider, and prefer non-fp8/bf16 serving if output fidelity matters. DeepSeek's cost win is real (V4 Flash ~$0.14/$0.28) — just pay the jurisdiction tax with hosting choice, not data exposure.
4. **Treat the Claude API as a scalpel, not a driver.** Use a metered Claude key for the specific things the subscription can't do well — Batch (-50%) bulk jobs that need Claude quality, or programmatic spillover — not as your everyday interactive engine.
5. **Mind the 15 Jun 2026 programmatic-pool change for headless/scheduled agents.** Agent SDK, `claude -p`, GitHub Actions and scheduled runs draw from a **separate monthly API-priced credit pool** ($100 at Max 5x / $200 at Max 20x), **not** your flat interactive allowance. If you automate parallel loops headlessly, budget for that pool — or route headless/background jobs to the cheap Gemini/DeepSeek key instead of burning Claude API credit. ([pricing][s-claude-price], 2026-06-24)

---

## Sources

All accessed **2026-06-24**. Items marked **(unconfirmed)** could not be verified against the primary source on this run (HTTP 403 or proxy denial); figures are from search-aggregator fallback and should be re-verified.

- **[s-claude-price]** Anthropic / Claude Platform Docs — Pricing (confirmed): <https://platform.claude.com/docs/en/about-claude/pricing>
- **[s-ds-price]** DeepSeek API Docs — Models & Pricing **(unconfirmed; 403, aggregator fallback)**: <https://api-docs.deepseek.com/quick_start/pricing>
- **[s-gemini-price]** Google Gemini API Pricing **(unconfirmed; 403, aggregator fallback)**: <https://ai.google.dev/gemini-api/docs/pricing>
- **[s-ds-cc]** DeepSeek API Docs — Claude Code integration **(unconfirmed; 403, official GitHub mirror used)**: <https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code> (mirror: <https://github.com/deepseek-ai/awesome-deepseek-agent/blob/main/docs/claude_code.md>)
- **[s-ccr]** claude-code-router (musistudio, community/unofficial) (confirmed): <https://github.com/musistudio/claude-code-router>
- **[s-ds-privacy]** DeepSeek Privacy Policy + government-restriction reporting + open-weight/hosting sources **(unconfirmed; primary 403, secondary corroboration)**: <https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy-2025-02-14.html>

[s-claude-price]: https://platform.claude.com/docs/en/about-claude/pricing
[s-ds-price]: https://api-docs.deepseek.com/quick_start/pricing
[s-gemini-price]: https://ai.google.dev/gemini-api/docs/pricing
[s-ds-cc]: https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code
[s-ccr]: https://github.com/musistudio/claude-code-router
[s-ds-privacy]: https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy-2025-02-14.html
