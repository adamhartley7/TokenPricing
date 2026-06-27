# Code Review: Cowork Tab Implementation

## Verdict: **REJECT**

The submission is **incomplete** — the code is literally truncated mid-statement. This alone prevents approval regardless of the quality of what's present.

---

## Score: 38/100

### Reasoning
The portions that exist show competent design instincts (zod schemas, allowlist canonicalization, audit hashing, promise-based confirmation gating). But this is a fragment of an implementation, not an implementation. The plan describes 5 major workstreams; the code delivers partial coverage of ~2 of them and **zero** coverage of provider abstraction, spend-guard integration, the agent orchestration loop, the UI, and tests — which are the *defining* requirements of the task ("multi-step agent harness", "provider-pluggable", "shares the same spend-guard gateway and cost meter").

---

## Strengths
- **Tool interface** uses zod with runtime validation (`schema.input.parse(args)`) — good defense against malformed model output.
- **Allowlist resolver** correctly canonicalizes with `path.resolve` + `fs.realpath`, handles the write-to-nonexistent-file case by validating the parent, and applies a belt-and-suspenders `path.relative` traversal check.
- **Confirmation gating** is promise-based and integrates cleanly into the executor before destructive ops run.
- Audit log captures before-hash and timestamp; classifier separates safe vs. destructive.

---

## Critical Issues (FIX-FIRST / REJECT blockers)

1. **Code is truncated.** `toolExecutor.ts` cuts off mid-`fs.mkdir` call. `write_file`, `list_dir`, `search`, and `run_command` cases are missing or incomplete. Non-compilable.

2. **Entire workstreams absent:**
   - **§1 Agent harness** — no execution loop, no plan→act→observe, no step limits, no abort/pause/resume, no state machine, no persistence/transcript, no progress events. This is the core of the task.
   - **§3 Provider abstraction** — completely missing. No provider interface, no tool-call normalization, no fallback parser.
   - **§4 Spend-guard / cost meter** — completely missing. The task explicitly emphasizes sharing the gateway/cost meter; not a single line addresses it.
   - **§5 UI & tests** — no UI components, no config surface, no tests despite the plan calling for path-allowlist edge-case tests and budget-halt tests.

---

## Specific Bugs / Weaknesses in Existing Code

1. **`startsWith(entry.root + path.sep)` is a prefix-collision risk if not careful** — it's mostly fine here, but combine it with the realpath logic: in the write branch, `return candidate` returns the *non-realpathed* candidate while the read branch returns `real`. Inconsistent — a symlinked parent could still be partially exploited because the candidate's own final segment isn't realpath-checked at write time.

2. **TOCTOU vulnerability**: `resolveAllowedPath` realpaths, then the executor later does `fs.readFile`/`mkdir` separately. A symlink swapped between resolution and use defeats the check. Needs `O_NOFOLLOW` / fd-based operations or re-validation.

3. **`run_command` has no sandboxing** — `execAsync` runs arbitrary shell. The `workingDir` is never validated against the allowlist in the shown code, and there's no command allowlist, env scrubbing, timeout, or output capping. Confirmation alone is insufficient mitigation for arbitrary shell exec.

4. **MD5 for audit hashes** — acceptable for change-detection but a poor choice; use SHA-256.

5. **Module-level singletons** (`allowlist`, `log`, `confirmationManager`) are global mutable state. No per-session/tenant isolation, no concurrency safety, audit log grows unbounded in memory with no persistence (contradicts §1 "step persistence / transcript logging" and §2 "audit log").

6. **Confirmation ID via `Math.random()`** — collision-prone and not cryptographically meaningful; use `crypto.randomUUID()`.

7. **`fileHash` returns `'none'` on error silently** — masks permission errors vs. genuinely-absent files; could corrupt audit integrity reasoning.

8. **No per-step/per-session budget cap enforcement anywhere**, despite being a hard requirement ("halt the agent when exceeded").

9. **`read_file` computes `beforeHash` *after* reading** the content into memory separately — redundant double read, and labeling it "before" for a read op is semantically odd.

10. **`ToolResult.error` field is defined but never populated** — errors thrown from `executeTool` propagate as exceptions rather than structured results, which the agent loop (absent) would need to observe.

---

## Discrepancies vs. Plan
| Plan item | Status |
|---|---|
| Agent loop, step limits, abort/resume | ❌ Missing |
| State machine, scratchpad, persistence, progress events | ❌ Missing |
| Allowlist resolver / traversal rejection | ⚠️ Partial, has TOCTOU/symlink gaps |
| Destructive gating + diff/preview | ⚠️ Gating present, **no diff/preview**, **no dry-run/sandbox** |
| Audit log | ⚠️ In-memory only, no persistence |
| Provider abstraction + normalization | ❌ Missing |
| Spend-guard + cost meter | ❌ Missing entirely |
| UI + config surface | ❌ Missing |
| Tests | ❌ Missing |

---

## Recommendation
Resubmit a complete implementation. At minimum the agent orchestration loop, provider abstraction, and spend-guard integration must exist and compile, since they are the explicit headline requirements. Then address the security gaps (TOCTOU, command sandboxing, hash algorithm) and add the required test coverage. The allowlist module is the strongest piece