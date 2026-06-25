# Advanced setup — offload to GLM/DeepSeek, add memory + search, fork a chat UI

This is the "configure, don't build from scratch" guide. It wires existing, verified tools so you get ~90%
of the dream — Opus plans, cheaper models do the bulk, with your own portable memory + web search — for
about **$18/mo + a tiny bit of Opus planning cost**.

> **Privacy first.** Your Claude export, the importer's output (`_memory_import/`), and any API keys are
> personal and are **git-ignored — never push them**. Hosted GLM / DeepSeek / mem0-cloud store data
> off-device (GLM & DeepSeek host in the PRC). For sensitive code, use the **local** memory backend and a
> Western-hosted or self-hosted model.

---

## 1. Web search for a swapped-in model (2 minutes)

Claude's built-in web search does **not** carry over when you route to GLM/DeepSeek. Add one search MCP
server instead (pick **one** — installing several makes the agent choose wrong):

```powershell
claude mcp add tavily-search npx -y tavily-mcp@latest
# then set your Tavily key (free tier: 1,000 searches/month) per the prompt
claude mcp list        # confirm it's connected
```

Alternatives: Brave Search, Exa. Manage with `claude mcp remove <name>`; scope with `--scope project`.

---

## 2. Persistent memory for any model (two paths — pick one)

Memory isn't Anthropic's to lend to GLM; you run your **own** memory layer via MCP, and every model
(GLM, DeepSeek, Claude) uses it.

### Path A — Cloud mem0 (easiest, ~5 min; data leaves your machine)
```powershell
npx mcp-add --name mem0-mcp --type http --url "https://mcp.mem0.ai/mcp" --clients "claude code"
```
Fast, but your memories live on mem0's servers. Fine for non-sensitive use.

### Path B — Local / self-hosted (private, EU-safe; more setup)
Two good options:
- **[`thedotmack/claude-mem`](https://github.com/thedotmack/claude-mem)** — captures every Claude Code
  session automatically and injects relevant context next time. This is also your **live `~/.claude`
  watcher** (item 4) — it runs on hooks, no separate watcher needed.
- **Self-hosted mem0** — run mem0 against a local vector store (Qdrant) so nothing leaves your device; see
  [`mem0-mcp-selfhosted`](https://mcpservers.org/servers/elvismdev/mem0-mcp-selfhosted). Heaviest, most private.

Other options worth knowing: [`nicolasbatistoni/claude-rag-memory`](https://github.com/nicolasbatistoni/claude-rag-memory),
[`zilliztech/memsearch`](https://github.com/zilliztech/memsearch), [`coleam00/claude-memory-compiler`](https://github.com/coleam00/claude-memory-compiler).

---

## 3. Import your Claude history (one-time)

Your export (Settings → Privacy → Export data) holds 182 conversations + your memory, far too big to "stuff"
into a context window — so we index it for retrieval (RAG). Turn it into clean Markdown:

```powershell
python import-claude-export.py --zip "C:\path\to\export.zip" --dry-run   # check the counts
python import-claude-export.py --zip "C:\path\to\export.zip"             # writes ./_memory_import/
```

Then ingest `_memory_import/` into whichever memory store you chose in step 2 (mem0 / claude-mem / LibreChat
RAG). `_memory_import/` is git-ignored.

**Why RAG, not stuffing:** GLM 5.2's 1M-token window is big but not infinite, and cramming everything in
degrades answer quality ("lost in the middle") and costs money + latency on *every* call. RAG pulls only the
relevant slice per task.

---

## 4. Live capture of new sessions

If you used **claude-mem** (Path B) it already captures every new Claude Code session via hooks — that's your
"constantly up-to-date" memory, no extra work. (mem0's Claude Code plugin captures at lifecycle points too.)

---

## 5. Orchestrator-worker: Opus plans, cheap models do the bulk

The subagents in `.claude/agents/` are pre-made: `bulk-implementer`, `researcher`, `test-writer` (workers) and
`final-reviewer` (stays on Opus — the quality gate). Your main session runs Opus for the hard plan + final
review; the workers do the volume.

### Option A — native, still Claude (simplest)
Workers run on Sonnet/Haiku (set in each agent's `model:` field, or globally with
`CLAUDE_CODE_SUBAGENT_MODEL`). Reliable, but still draws your Claude plan. Documented to cut cost ~40% vs
all-Opus.

### Option B — GLM/DeepSeek workers, OFF your Claude weekly limit
Run Claude Code under [`claude-code-router`](https://github.com/musistudio/claude-code-router) and route the
worker/background model to GLM 5.2:
```powershell
npm install -g @musistudio/claude-code-router
# copy this repo's claude-code-router/config.example.json to ~/.claude-code-router/config.json, add keys
ccr code
```
The example config keeps `default`/`think` on Opus and sends `background`/`longContext` to GLM. Documented to
cut token cost ~5–10× with little quality loss. **Verify the exact GLM model id** at
<https://docs.z.ai/guides/llm/glm-5.2> before relying on the placeholder in the config.

---

## 6. Quick single-session offload (no router)

For ad-hoc "just don't touch my Claude limit" work, use the launchers in this repo — they point one terminal
window at a cheaper model and pass through any `claude` flags:
```powershell
./glm.ps1        # GLM 5.2 (Z.ai)  — see glm.ps1
./deepseek.ps1   # DeepSeek V4 Pro — see deepseek.ps1
```
Close the window to return to normal Claude.

**Long / overnight runs:** `glm-overnight.ps1` bundles GLM routing + a Windows keep-awake (auto-restored
on exit). It asks permissions by default; add **`-Unattended`** to also pass `--dangerously-skip-permissions`
so Claude Code never stops to ask — that's what makes it truly hands-off. `cd` into the target project
first, then run it; pass an initial task prompt as an argument if you like:
```powershell
cd C:\my\project
C:\path\to\TokenPricing\glm-overnight.ps1 -Unattended "Work through TODO.md top to bottom, committing after each task."
```
Run **one window per project** to do several at once. Use `-Unattended` only in a **git repo** so
`git diff` lets you review/undo everything in the morning, and only with tasks you're comfortable
running unattended.

---

## 7. Your personalized chat/Cowork app — fork LibreChat

You can't make Anthropic's Cowork run GLM, but you can run your **own** modifiable replica.
[**LibreChat**](https://github.com/danny-avila/LibreChat) is the base: open-source, self-hostable, supports
custom **Anthropic-compatible** endpoints, MCP, RAG, and Presets.

1. Clone & run it (Docker quickstart in its README).
2. Add GLM as a **custom endpoint**: `baseURL: https://api.z.ai/api/anthropic`, your Z.ai key,
   `provider: "anthropic"`. (Add DeepSeek/Qwen the same way for model-switching.)
3. Use **Presets** for the controls you wanted: **max tokens** = answer length; **system prompt** = answer
   form/format; the model's **thinking/reasoning** parameter = "time spent thinking".
4. Enable **MCP** so the same search + memory servers from steps 1–2 plug in, and turn on **RAG** over
   `_memory_import/` so it knows your history.

This is the "do whatever I want with it" app — fork it and customize freely. It's days, not the multi-week
greenfield build.

---

## 8. See & drive it all — ClaudeLens (desktop, GLM-routed)

[**ClaudeLens**](https://github.com/giulio333/ClaudeLens) is an open-source (MIT) desktop app that
reads your local `~/.claude/` folder and gives you a visual UI to browse past sessions, edit your
memory / `CLAUDE.md` / skills / agents, replay sessions, and continue them via an **embedded terminal**
or an **in-app chat**. Because it reads the same `~/.claude/`, it surfaces the orchestrator subagents
from step 5 and everything your routed terminals create — one window over the whole setup.

It can't be embedded in the published web page (it's a desktop program that needs your local files);
instead we add it to the toolkit and point it at GLM so it stays off your Claude limit.

**Install (Windows — experimental):**
```text
1. Download the Windows .exe from https://github.com/giulio333/ClaudeLens/releases
2. Run the installer. Windows SmartScreen may warn -> "More info" -> "Run anyway".
```
(macOS/Linux builds exist too; Windows is flagged experimental by the project.)

**Run it routed to GLM 5.2 (off your Claude limit):**
```powershell
./claudelens.ps1     # sets ANTHROPIC_BASE_URL/_AUTH_TOKEN to Z.ai, then opens ClaudeLens
```
This reuses the same `.glm-key` as `glm.ps1` (step 6). The app inherits the env vars from the launching
window, so its terminal and chat run on GLM. If `claudelens.ps1` can't find the app, it prints install
help and lets you paste/save the path.

**Caveats:**
- **Quit ClaudeLens fully before relaunching via the script** — it's single-instance, so an
  already-open window will be refocused and ignore the new GLM routing.
- The **embedded terminal** definitely inherits GLM; the **in-app chat** (Claude Agent SDK) should too,
  since it reads the same `ANTHROPIC_*` env — verify with the checks below.
- ClaudeLens sends anonymous telemetry by default; opt out under **Settings → Privacy**.
- Same privacy caveat as everywhere here: the hosted Z.ai endpoint stores data in the PRC — use a
  local/Western model for sensitive code.

**Verify:**
1. `./claudelens.ps1` → green "Routed to GLM 5.2" banner, ClaudeLens opens.
2. In its embedded terminal: `echo $env:ANTHROPIC_BASE_URL` → should print `https://api.z.ai/api/anthropic`.
3. Send a test message in the in-app chat; confirm your Z.ai usage ticks up and your Claude usage does not.
4. Confirm it lists your existing sessions and shows `.claude/agents/`.

---

## Reality check / honest limits
- GLM & DeepSeek are a notch below Opus on the hardest agentic work, and tool-use via a router is slightly
  less reliable than native Claude — keep `final-reviewer` on Opus and verify on real tasks.
- Many non-Claude prices are aggregator-sourced (official pages blocked the fetch) — re-verify before spending.
- This is guidance, not financial advice.
