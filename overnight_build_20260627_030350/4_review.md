# Code Review: 7C's Cowork Tab (Phase 4)

## Critical Finding: The Submission Is Fundamentally Incomplete

This review is severely constrained because **the implementation is truncated and self-contradictory**. Let me be specific.

---

## Discrepancies (Blocking)

### 1. The output is cut off mid-file — twice
- **Build Pass 1, File 3 (`coworkfs.py`)** terminates at `class PathDenied(Exceptio` — literally mid-token. This is the **single most security-critical file in the entire task** (path canonicalization, symlink/junction escape prevention). It does not exist.
- **Build Pass 2, File 1 (`cowork_config.py`)** terminates at `"""Maximu` inside `load_budget()`. Incomplete.

### 2. Two incompatible versions of `cowork_config.py` were delivered
- **Pass 1** defines `cowork_config.py` as allowlist-only, documented to use env var `COWORK_ALLOWLIST` → JSON → empty.
- **Pass 2** redefines the *same file* with a totally different API: budget, provider, **`OPENAI_API_KEY`**, `is_allowed()`, `load_provider()` defaulting to `'openai'`.

Which one wins? They overwrite each other. This is not a coherent build.

### 3. Provider abstraction is WRONG — contradicts the entire architecture
The task is explicit: providers are **Anthropic (Opus/Sonnet/Haiku) and DeepSeek (V4-Pro/Flash)**, routed through the gateway's spend-guard. Pass 2 introduces:
- `load_openai_api_key()`
- `OPENAI_API_KEY` env var
- `load_provider()` defaulting to `'openai'`

**OpenAI is not a provider in this system.** This indicates the model lost the plot and pattern-matched to a generic agent template. It also means there is **zero wiring to `anthropic.py` / `deepseek.py` / `spendguard.py`** — the explicit requirements 4 and 5.

### 4. Pass 2 contradicts its own stated deliverables
Pass 2 promises "provider abstraction wiring, spend-guard integration, and a terminal-based UI visualization." Then delivers a partial config file and stops. A **terminal-based UI** also directly violates the UI requirement, which demands a **web "Cowork" tab in `chat.html`** reusing existing CSS.

---

## What's Missing Entirely (against the spec)

| Requirement | Status |
|---|---|
| 1. Agent loop (plan→act→observe→reflect) | ❌ Not present |
| 2. Scoped FS access (`coworkfs.py`) | ❌ Truncated at line 1 of the class |
| 3. Destructive op confirmation gating | ❌ Not present |
| 4. Provider-pluggable (Anthropic/DeepSeek) | ❌ Wrong (OpenAI) |
| 5. Shared spend-guard + cost meter | ❌ No integration |
| 6. Web UI in `chat.html` | ❌ Not present (terminal UI proposed instead) |
| Route `POST /cowork/run` in `app.py` | ❌ Absent |
| Tests / "41 tests still pass" evidence | ❌ Absent |
| Run section (PowerShell) | ❌ Absent |

**At least 4 of the 5 promised "core files" + all 4 "Pass 2 components" are missing or stubbed.**

---

## Strengths (the little that exists)

1. **`cowork_config.py` (Pass 1) allowlist logic is genuinely good:**
   - Deny-by-default is correctly implemented (empty list → nothing accessible).
   - Dedup with canonicalization-before-compare is the right order.
   - Sensible resolution precedence (env → JSON → empty).
   - Tolerant of non-existent dirs with `OSError` fallback — reasonable for Windows.

2. **Security docstrings show correct understanding** — the `coworkfs.py` docstring correctly describes `realpath` for junction/reparse resolution, the `path.relpath` belt-and-suspenders check, and new-file parent validation. The *intent* matches the spec precisely.

3. **Style matches** the described codebase conventions (module docstrings, typed signatures, `pathlib`).

---

## Weaknesses Beyond Incompleteness

- **`is_allowed()` in Pass 2 uses `os.path.commonpath`** instead of the spec-mandated `os.path.relpath` "belt-and-suspenders" check. `commonpath` has a known prefix-collision risk class (`C:\allowed` vs `C:\allowedother` is handled by commonpath, but the spec explicitly asked for the `relpath`-startswith-`..` pattern, which the author then *failed to use* in their own helper). Inconsistent with their own Pass 1 docstring.
- **No symlink-escape test, no junction test** — the headline security feature is entirely unverified.
- **Empty `allow: []` allowlist.json** ships a non-functional default with no example config to demonstrate intended use.

---

## Score: 12 / 100

**Reasoning:** The only complete, runnable artifact is one allowlist config file and one (duplicated, partially superseded) config module. That config logic is competent — hence non-zero. But the deliverable explicitly demanded *complete, runnable files, no placeholders, no "rest unchanged,"* and the submission delivers neither the agent loop, the security FS layer, the confirmation gating, the correct provider wiring, the web UI, the route, nor the Run section. It also introduces an architecturally invalid provider (OpenAI) and proposes a terminal UI that violates the spec.

---

## Verdict: **REJECT**

This is not a fixable draft — it's roughly 10% of the task with two contradictory config files and a wrong provider model. Resubmit with:
1. A single, complete `cowork_config.py` using **Anthropic + DeepSeek only**.
2. Complete `coworkfs.py` with the `realpath` + `relpath` checks **and tests** proving symlink/junction escapes are rejected.
3. The agent loop engine, confirmation gating, `POST /cowork/run` route, and the **web** Cowork tab in `chat.html`.
4. Proof the 41 existing tests pass + the PowerShell Run section.