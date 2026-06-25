# CLAUDE.md — read this first

This file is loaded automatically at the start of every Claude Code session (web or local). It is the
handoff so a fresh chat doesn't have to be re-told everything. **The owner is a non-developer on Windows
who had never used a terminal before — keep all instructions concrete, plain-English, and verify the
environment before giving steps.**

## What this project is
- **`index.html`** — a single-page cost & strategy calculator comparing Claude, DeepSeek, Gemini, OpenAI,
  Qwen, and local models (live on GitHub Pages). This is the original project.
- **A local Windows toolkit** (`*.ps1`) for running Claude Code on cheaper models (GLM / DeepSeek)
  **off the user's Claude weekly limit**, plus docs and a history importer.

## The decision so far (why the toolkit exists)
The owner is on **Claude Max 5x** and hits the **weekly limit early in the week**. The goal: route work
to a cheaper metered model for the rest of the week.
- **DeepSeek V4 Pro = cheapest.** Their whole heavy June (~916M tokens, ~$1,248 Claude-equivalent — see
  `usage.json`) would cost **~$39 on DeepSeek metered**; finishing out a week ≈ **~$5**. It's cheap
  because their usage is ~92% cache reads and DeepSeek cache hits are nearly free ($0.003625/M).
- **GLM 5.2 = pricier but more reliable** for unattended runs (officially supported by Claude Code).
  Same month ≈ ~$350 metered.
- **Rule of thumb:** DeepSeek for cheap watched work; GLM for hands-off overnight runs where reliability
  matters. Both assume model-side prompt caching works through the route — verify after a day of use.

## File map
| File | What it does |
|------|--------------|
| `glm.ps1` | Open Claude Code routed to GLM 5.2 (Z.ai). Key cached in `.glm-key`. |
| `deepseek.ps1` | Same, routed to DeepSeek V4 Pro. Key cached in `.deepseek-key`. |
| `glm-overnight.ps1` | GLM + keeps PC awake. `-Unattended` adds `--dangerously-skip-permissions` for hands-off runs. |
| `deepseek-overnight.ps1` | Same as above, routed to DeepSeek (cheapest overnight option). |
| `claudelens.ps1` | Opens the ClaudeLens desktop app routed to GLM. |
| `index.html` | The cost calculator (GitHub Pages). |
| `REPORT.md` | Full written cost/strategy analysis with sources. |
| `ADVANCED-SETUP.md` | GLM/DeepSeek routing, memory/RAG, MCP, orchestrator-worker, LibreChat fork. |
| `sync-usage.ps1` | Runs `ccusage`, writes `usage.json` (local only). |
| `import-claude-export.py` | Turns a Claude data-export zip into Markdown for RAG. |

## ⚠️ CRITICAL — branch
**All of the above lives ONLY on the branch `claude/token-app-deepseek-cost-analysis-fvsql5`.**
The `main` branch contains just `README.md`. If you clone/checkout `main`, the folder looks empty and
the scripts won't run. **Be on the work branch.** (Worth merging the branch into `main` eventually so a
default clone isn't empty — ask the owner first.)

## How to run it (Windows, beginner-friendly)
1. **GitHub Desktop** → top **"Current Branch"** dropdown → select
   `claude/token-app-deepseek-cost-analysis-fvsql5`. The files appear in the folder.
2. **Repository → Open in PowerShell.** Confirm the prompt starts with **`PS`** (NOT a `C:\...>` prompt —
   that's Command Prompt, where these scripts fail; if so, type `powershell` and Enter).
3. Allow scripts for this window: `Set-ExecutionPolicy -Scope Process Bypass`
4. Run it: `.\deepseek-overnight.ps1`  (add `-Unattended "your tasks..."` for hands-off overnight).
5. **Paste the API key when prompted** (right-click pastes). The key is **invisible as you paste** — no
   dots/stars — that is normal. Press Enter, then `Y` to save it (won't ask again).

## Privacy / safety
- API keys live in `.glm-key` / `.deepseek-key`, which are **git-ignored — never commit them**.
- `-Unattended` skips permission prompts; use **only in a git repo** so `git diff` lets you review/undo.
- Hosted GLM & DeepSeek store data on PRC servers; use OpenRouter / self-host for sensitive code.

## ⚠️ MISTAKES MADE DURING SETUP — DO NOT REPEAT THESE
The first setup attempt went badly because of assumptions. Any future session must learn from these:

1. **Don't give "open the folder / run the script" steps before confirming the repo is cloned on the
   user's PC.** Initially everything was only in the cloud + on GitHub; their laptop had nothing.
   → Verify it's actually cloned locally first.
2. **Don't assume `main` has the files.** Everything is on the work branch; `main` is just `README.md`.
   A default clone is empty — this caused a `'.ps1' is not recognized` error and a lot of wasted time.
   → Make sure the user is on `claude/token-app-deepseek-cost-analysis-fvsql5`.
3. **Don't assume PowerShell.** GitHub Desktop's "Open in…" can launch **Command Prompt**, where
   `Set-ExecutionPolicy` and `.ps1` scripts fail. → Check the prompt starts with `PS`; if not, run
   `powershell` first.
4. **The API-key prompt only appears when the script actually runs** — it is not a separate earlier
   step. Earlier errors stopped the script before it could ask, which confused the user. → Explain this.
5. **The user is a non-developer new to the terminal.** → Verify environment state (cloned? which
   branch? which shell? is `claude` installed?) BEFORE giving multi-step instructions. Don't assume and
   backtrack — it's exhausting for the user. Be concrete, check one thing at a time when stuck.
