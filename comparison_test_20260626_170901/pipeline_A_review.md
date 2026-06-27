# Code Review: Cowork Tab Implementation

## Verdict: **REJECT**

This implementation is **incomplete** — it does not satisfy the task or its own plan. Multiple files are truncated, and the code that *does* exist contains serious safety bugs that directly undermine the stated security goals (which are the core of the task).

---

## Score: 28/100

### Reasoning
The task's central value proposition is *safety*: scoped file access, allowlist enforcement, no destructive ops without confirmation. The submitted code fails to deliver a working version of any of these, has at least one critical security bug in the part that *is* written, and is literally cut off mid-function. Of the 5 plan sections, only fragments of sections 1 and 2 appear. There is no orchestration engine, no provider/spend-guard integration, no UI, no tests — i.e. ~70% of the plan is entirely absent.

---

## Critical Issues (must fix)

### 1. Code is truncated — incomplete submission
`sandbox.ts` ends mid-function inside the `EDIT` preview case (`//` with nothing after). The `classifyOperation` switch never returns for `EDIT`/`SHELL`, the class never closes, and no other methods (`write`, `delete`, `edit`, staging/commit/revert) exist. This is not runnable.

### 2. Path validation is broken (security-critical bug)
```ts
const allowed = this.allowlist.some(entry => {
  const normalizedEntry = entry.path.endsWith(path.sep) ? entry.path : entry.path + path.sep;
  return resolved.startsWith(normalizedEntry);
});
```
- A `resolved` path that equals the allowlist dir *exactly* (no trailing sep) is rejected — you can't operate on the dir root itself, minor.
- **Symlink escape is not handled at all.** The plan explicitly requires "rejecting … symlinks escaping the scope." `path.resolve` does no filesystem resolution, so a symlink inside the allowlist pointing outside passes validation. This is a real sandbox escape. You need `fs.realpath` on both the resolved path and the allowlist base, then compare — with care for non-existent files (resolve the nearest existing parent).
- `startsWith` on a normalized string prefix is fragile; prefer `path.relative(base, resolved)` and check the result does not start with `..` and is not absolute.

### 3. `readOnly` allowlist flag is never enforced
`IAllowlistEntry.readOnly` exists in the type and config but `resolveAndValidate` never checks it. A write to a read-only allowlisted dir would be permitted. The allowlist's read-only semantics are dead.

### 4. Broken existence check / Promise misuse in `WRITE` classification
```ts
const isNew = op.path ? !fs.stat(op.path).then(() => true).catch(() => false) : true;
```
`fs.stat(...).then(...)` returns a **Promise**, and `!Promise` is always `false`. So `isNew` is always `false` ⇒ every write is classified destructive (and the logic is incoherent anyway). Also it uses the raw `op.path` rather than the validated absolute path, and synchronously negates an async value. This must be `await`ed inside an async classifier.

### 5. "No destructive ops without confirmation" is not implemented
The harness/orchestrator that would gate `IPlannedStep.isDestructive` behind `IConfirmationRequest`/`IConfirmationResponse` does not exist. The types are defined but unused. The core safety guarantee is absent.

### 6. Default allowlist defeats the security model
```ts
defaultAllowlist: [{ path: process.env.HOME || ... || '/', readOnly: false }]
```
Defaulting to the **entire home directory (or `/`)** with `readOnly: false` is the opposite of "scoped" access. A misconfigured/empty env yields a writable root allowlist. This should default to empty (deny-all) and force explicit grants.

---

## Major Gaps vs. Plan

- **Section 1 (Agent harness / orchestration):** No step engine, no plan→act→observe→reflect loop, no persistence/pause/resume/rollback, no tool registry, no circuit breaker / max-iteration enforcement. Only the *types* exist.
- **Section 3 (Provider + spend-guard + cost meter):** Completely missing. No provider abstraction reuse, no spend-guard gateway routing, no cost meter integration, no per-step cost attribution, no budget-halt logic. This is a primary task requirement and is 0% delivered. `totalCost`/`budgetLimit`/`cost` are unused fields.
- **Section 4 (UI):** No frontend whatsoever.
- **Section 5 (Testing/rollout):** No tests (the explicitly-required adversarial path-traversal/scope-escape tests), no feature flag, no telemetry, no docs.
- **Transactional staging area / dry-run / revert:** Referenced via `stagingDir` config but not implemented.

---

## Minor Issues / Nits

- `diffLines` is imported but never used.
- `IOperationPreview.diff` for overwrite returns a prose string ("File will be overwritten…"), not an actual diff — the plan requires a diff preview for destructive ops.
- `removeAllowedDir` compares against raw `dirPath` but stored paths are `path.resolve`'d — removal will silently fail for relative inputs. Normalize before comparing.
- `resolveAndValidate` resolves relative paths against `process.cwd()`, which may differ from the intended session scope — agent-supplied relative paths could resolve unpredictably. Resolve against an explicit session root instead.
- `Record<string, any>` / `data?: any` weaken type safety throughout.
- `IStep.cost` and `totalCost` are numbers with no currency/unit contract tying them to the shared cost meter.

---

## Strengths

- The `shared/types.ts` model is reasonably thought-through: clear state machine (`SessionStatus`), operation classification, planned-