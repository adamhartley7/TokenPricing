# 7C's — Central Executive ("Seven Seas")

A personal, self-hosted, multi-provider AI workbench. **Phase 0 + Phase 1** ship the **Chat tab**:
multi-provider chat (Claude + DeepSeek) through **LibreChat**, with the brief's #1 non-negotiable —
a **spend cap enforced before every paid call** — provided by a small local **spend-guard gateway**
that all provider traffic routes through. The gateway also meters cost per provider (a live meter)
and is the reusable spine for the later Code and Cowork tabs.

```
LibreChat (Docker, your Chat UI)
   │  DeepSeek → OpenAI-shape       Claude → Anthropic-shape (ANTHROPIC_REVERSE_PROXY)
   ▼
spend-guard gateway  (FastAPI, http://localhost:8787)
   1. estimate input tokens   2. worst-case cost = input + max_tokens·output
   3. REFUSE (HTTP 402) if over the per-request / session / day cap — before forwarding
   4. forward (stream pass-through)   5. meter ACTUAL cost → ledger → /meter
   ▼
Anthropic API (your key)        DeepSeek API (your key)
```

> Keys live **only** in the gateway's `.env` (or a git-ignored key file). LibreChat is given dummy
> keys — the gateway injects the real ones and strips whatever the client sends.

---

## Prerequisites (install once)

| Tool | Why | Get it |
|---|---|---|
| **Python 3.11+** | runs the gateway | <https://www.python.org/downloads/> (tick "Add to PATH") |
| **Docker Desktop** | runs LibreChat | <https://www.docker.com/products/docker-desktop/> |
| **Git** | clone LibreChat | <https://git-scm.com/download/win> |

Everything below is **Windows PowerShell**. Run commands from the repo root unless told otherwise.

---

## Part A — the spend-guard gateway (5 minutes)

```powershell
cd "7Cs\gateway"

# 1. Configure. Copy the example, then add your keys + tune caps.
Copy-Item .env.example .env
notepad .env          # set DEEPSEEK_API_KEY / ANTHROPIC_API_KEY and the CAP_* values
#  (If you already cached a DeepSeek key via deepseek.ps1, the gateway reads the repo-root
#   .deepseek-key automatically — you can leave DEEPSEEK_API_KEY blank.)

# 2. Start it (creates the venv + installs deps on first run, opens the cost meter).
cd ..
./start-7Cs.ps1
```

Confirm it works:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/health     # shows which keys are present + your caps
```

The cost meter opens at **<http://localhost:8787/>**. Leave the gateway window open while you work.

### Run the tests / a live check (optional)

```powershell
cd "7Cs\gateway"
./.venv/Scripts/python.exe -m pytest -q      # 22 tests: pricing, cap-refusal, ledger, streaming
```

---

## Part B — LibreChat as the Chat tab (10 minutes)

```powershell
# 1. Clone LibreChat somewhere OUTSIDE this repo.
cd ..\..                       # or wherever you keep projects
git clone https://github.com/danny-avila/LibreChat.git
cd LibreChat

# 2. Create its .env, then add the 7C's entries.
Copy-Item .env.example .env
#   Open .env and append the lines from 7Cs/librechat/.env.example
#   (DEEPSEEK_API_KEY=gateway-managed, ANTHROPIC_API_KEY=gateway-managed,
#    ANTHROPIC_REVERSE_PROXY=http://host.docker.internal:8787/anthropic, ANTHROPIC_MODELS=…)

# 3. Drop in our config (custom DeepSeek endpoint + mount).
Copy-Item "<repo>\7Cs\librechat\librechat.yaml" .
Copy-Item "<repo>\7Cs\librechat\docker-compose.override.yml" .

# 4. Bring it up.
docker compose up -d
```

Open **<http://localhost:3080>**, create a local account, and in the chat bar pick **DeepSeek →
deepseek-v4-flash**. Send a message. You should see a reply, and the gateway meter at
<http://localhost:8787/> increment with the cost.

> Tip: `./7Cs/start-7Cs.ps1 -LibreChatPath C:\path\to\LibreChat` copies the two files in and runs
> `docker compose up -d` for you (still add the `.env` entries first).

### The §5.1 chat controls
See [`librechat/presets/README.md`](librechat/presets/README.md): model + **Max Output Tokens**
(length) + **reasoning_effort** (depth) + a paste-in **system prompt** (format: Markdown /
single-file HTML artifact / produce-a-file). Save these as **Presets** to pick per request.

---

## Spending — how the cap works

Before every paid call the gateway computes a **worst-case** cost =
`input_tokens × input_price + max_tokens × output_price` (input tokens are counted exactly for
Claude via the free `count_tokens` endpoint, and via DeepSeek's tokenizer/heuristic otherwise). If
that worst case would breach **any** of the three caps it returns **HTTP 402 and never forwards** —
nothing is spent. Caps live in `7Cs/gateway/.env`:

```
CAP_PER_REQUEST_USD=0.50     # most one message may cost
CAP_PER_SESSION_USD=2.00     # this gateway run
CAP_PER_DAY_USD=5.00         # rolling UTC day
```

Tighten a single message with **Max Output Tokens**, or send a header `x-7Cs-cap: 0.05`. The meter
(`/meter`) shows running spend per session / day / provider. Refusals are logged but never counted
as spend.

---

## Add a new provider or model (the modular path)

Adding a provider = **one price entry + one ~40-line adapter + one route + one LibreChat block** — no
surgery:

1. **Price it** — add the model to [`gateway/pricing.json`](gateway/pricing.json) (input/output per
   1M, cache rate, a `confirmed` flag + source).
2. **Adapter** — add `gateway/providers/<name>.py` subclassing `Provider` (see
   [`providers/deepseek.py`](gateway/providers/deepseek.py) for OpenAI-shape, or
   [`providers/anthropic.py`](gateway/providers/anthropic.py) for Anthropic-shape). You only define
   auth headers, the stream-usage accumulator, and (if needed) `_enable_stream_usage`.
3. **Register** — add it to `app.state.providers` in [`gateway/app.py`](gateway/app.py) and add a
   `@app.post("/<name>/…")` route that calls `_handle("<name>", "<subpath>", request)`.
4. **Expose in LibreChat** — add a custom endpoint block in `librechat/librechat.yaml` whose
   `baseURL` is `http://host.docker.internal:8787/<name>/v1`.

Adding just a **model** to an existing provider = add it to `pricing.json` and the LibreChat endpoint's
`models.default` list. (Gemini, intentionally deferred to a later phase, is exactly this plus a
small `maxOutputTokens` adapter.)

---

## Security & git safety

- **Never commit a key.** Real keys live only in `7Cs/gateway/.env` or a repo-root `.deepseek-key`
  / `.anthropic-key` — all git-ignored. LibreChat gets dummies. The gateway never logs a key.
- The gateway binds `0.0.0.0` so the LibreChat container can reach it. On a personal machine the
  caps + Windows Firewall are the backstops. For stricter isolation, run the gateway as a container
  (`gateway/Dockerfile`) published only to `127.0.0.1` and reached over the Docker network.
- Hosted DeepSeek stores data in the PRC — for sensitive code set `DEEPSEEK_BASE_URL` to a Western
  host / self-host (a one-line `.env` change).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/health` shows `deepseek:false` | add `DEEPSEEK_API_KEY` to `7Cs/gateway/.env` (or a repo-root `.deepseek-key`) and restart the gateway |
| LibreChat reply errors / can't reach gateway | the gateway must bind `0.0.0.0` (default) and LibreChat's URLs must use `host.docker.internal`, not `localhost` |
| `UnicodeEncodeError … ﻿` in a key | a key file saved with a BOM — the gateway already strips it (`utf-8-sig`); re-save without BOM if you hand-edit |
| Port 8787 in use | start with `-Port 9090` and update the `baseURL`/`ANTHROPIC_REVERSE_PROXY` ports |
| Claude not answering | confirm `ANTHROPIC_REVERSE_PROXY` is set in LibreChat's `.env`; or switch to the commented custom-endpoint block in `librechat.yaml` |

---

## What's intentionally NOT in this version

- A literal per-message **dollar field** in the chat bar (LibreChat has none) — caps are enforced in
  the gateway; tighten per message via Max Output Tokens or the `x-7Cs-cap` header.
- **Gemini** (Claude + DeepSeek only for v1), **memory/RAG** (Phase 2), the **Code** orchestrator
  tab (Phase 3), and the **Cowork** tab (Phase 4). All build on this same gateway.
