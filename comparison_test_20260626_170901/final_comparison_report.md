# Final Comparison Report
**Date:** 2026-06-26 17:28:22
**Task:** Build a Cowork tab for the 7C's app — a multi-step agent harness with scoped file access, allowlisted directories, no destructive ops without confirmation, and provider-pluggable, sharing the same spe

## Pipeline Summary

| Pipeline | Models | Plan Tokens | Build Tokens | Review Tokens | Est. Cost |
|----------|--------|-------------|--------------|---------------|-----------|
| A (Opus->DeepSeek->Opus) | claude-opus-4-8->deepseek-v4-pro->claude-opus-4-8 | 1133 | 4800 | 5872 | $0.099775 |
| B (Full DeepSeek) | deepseek-v4-pro->deepseek-v4-pro->deepseek-v4-pro | 1089 | 4615 | 3712 | $0.007206 |

---

## Meta-Review: Opus
# Comparative Evaluation

## Pipeline A (Opus→DeepSeek→Opus)

### Plan (Opus)
Strong, well-structured plan. Four clearly delineated sections mapping directly to task requirements: agent harness, scoped file access/safety, provider-pluggable + shared spend-guard, and UI. Uses concrete mechanisms (plan→act→observe→reflect loop, transactional staging, circuit breakers, symlink/traversal rejection, cost attribution per-step). The plan section 4 is itself truncated ("confirmation moda…"). Otherwise the most thorough plan of the two.

### Build (DeepSeek)
Delivered a coherent `types.ts` with thoughtful enums and interfaces (SessionStatus, OperationType, IConfirmationRequest, ISessionState, etc.). The types model the safety domain well. **However, the build is severely truncated** — it cuts off at "cowork-tab/config/cowork." The actual implementation (sandbox, orchestrator, provider integration, UI) is essentially absent. Only the type scaffolding exists.

### Review (Opus)
This is the standout artifact. The review is honest, specific, and technically correct. It:
- Catches that the code is truncated and unrunnable.
- Identifies a **genuine security-critical bug**: `path.resolve` does no filesystem resolution, so a symlink inside the allowlist escapes the sandbox — exactly the threat the task names. The recommended `fs.realpath` fix is correct.
- Notes the exact-match allowlist edge case.
- Correctly scores low (28/100) and rejects, with reasoning tied to the task's core value proposition (safety).

The review demonstrates real evaluative rigor. The problem: the review is reviewing code (`sandbox.ts`) that **is not present in the build output shown** — the build only produced `types.ts` before truncating. So either the harness truncated the build display, or the reviewer is partly hallucinating the reviewed file. This is a discrepancy, though the security insight itself is valid and the reviewer's overall verdict (incomplete) is correct.

---

## Pipeline B (Full DeepSeek)

### Plan (DeepSeek)
Decent, covers all four requirement areas in prose bullets: harness/provider abstraction, scoped FS + confirmation, spend-guard/cost meter reuse, UI visualization. Less concrete than A's plan (no explicit loop architecture, no staging/rollback, no circuit breakers, no symlink handling mentioned). Adequate but shallower on the safety mechanisms that are the task's crux.

### Build (DeepSeek)
Delivered a React hook (`useCoworkAgent.ts`) with a reducer-based state machine, well-typed events (PLAN_RECEIVED, CONFIRMATION_REQUIRED, COST_UPDATE, etc.). This is clean frontend state management and includes the confirmation flow and cost/budget tracking in state — relevant to the task. **But this is also truncated** (cuts off mid-reducer) and is purely the UI layer. The actual safety-critical backend (sandbox, allowlist enforcement, provider gateway, spend-guard wiring) is entirely missing. The most security-sensitive part of the task is unaddressed.

### Review (DeepSeek)
**Empty.** The review section produced no output at all. This is a pipeline failure for the final stage — no quality gate, no critique, no verdict.

---

## Head-to-Head

| Dimension | Pipeline A | Pipeline B |
|---|---|---|
| Plan quality | Stronger, concrete, safety-aware (8.5/10) | Adequate, shallower (6.5/10) |
| Build completeness | Truncated, only types layer (3/10) | Truncated, only UI hook (3.5/10) |
| Build relevance to safety core | Types model safety domain | UI state, ignores backend safety |
| Review quality | Excellent, catches real security bug | **Missing entirely (failed)** |
| Self-consistency | Reviews file not shown (discrepancy) | N/A — no review |
| Overall coherence | High | Medium |

### Scoring

| Pipeline | Plan | Build | Review | Weighted Score /100 |
|---|---|---|---|---|
| **A** | 85 | 30 | 90 | **58** |
| **B** | 65 | 35 | 0 (failed) | **33** |

**Rationale:** Both builds are incomplete and truncated, so neither delivers a working Cowork tab. A wins decisively on the bookends: a more rigorous, safety-focused plan and a genuinely excellent, technically correct review that catches the exact class of vulnerability the task warns against. B's review stage completely failed (no output), removing any quality gate and leaving the build unevaluated.

### Cost & Value

| Pipeline | Cost | Score | Value/$ (score/cost) |
|---|---|---|---|
| **A** | $0.099775 | 58 | ~581 |
| **B** | $0.007206 | 33 | ~4,579 |

(Cost figures as provided; token-level recomputation not possible without raw counts, so I use stated costs.)

---

## Verdict

- **Higher absolute quality: Pipeline A.** It produced the best single artifact in the whole comparison (the Opus review with a real, actionable security finding) and a stronger plan. Its weakness is the truncated build and a review-vs-build consistency gap.
- **Higher value-per-dollar: Pipeline B**, by a wide margin (~8× cheaper), but it suffers a hard failure — the review stage produced nothing, so the pipeline has no final verification and ships an unreviewed, partial UI-only build.

**Recommendation:** For this task, where the entire point is *safety enforcement*, Pipeline A's reasoning is worth the premium — but neither pipeline delivered a usable implementation. If reliability matters, A is the choice despite cost; B is only attractive if its review-stage failure is fixed and a cheaper model can still catch the symlink/allowlist class of bugs that A's Opus reviewer caught and B's pipeline never even examined.

---

## Meta-Review: DeepSeek
## Pipeline Comparison

Both pipelines attempted to design and build a Cowork tab, but **neither produced a working or acceptable implementation**. They failed to deliver the core requirements: a multi‑step agent harness, safe scoped file access, destructive‑op confirmation, and provider‑pluggable integration with the shared spend‑guard gateway. The difference lies in the depth of planning, the quality of the partial code, and the presence of a self‑review.

| Pipeline | Score (out of 100) | Cost (USD) | Value‑per‑Dollar (Score / Cost) |
|----------|--------------------|------------|---------------------------------|
| **A** (Opus → DeepSeek → Opus) | 25 | $0.099775 | ~250.6 |
| **B** (Full DeepSeek)          | 10 | $0.007206 | ~1388.1 |

### Detailed Reasoning

#### Pipeline A
- **Plan** (Opus): Excellent. It covers a structured agent loop, sandboxed filesystem with symlink handling, transactional staging, provider abstraction, spend‑guard integration, and a detailed UI design. All task requirements are addressed.
- **Build** (DeepSeek): Severely incomplete. Only TypeScript type definitions and a fragment of a sandbox class are provided. The code is truncated mid‑function. It implements none of the promised features (no orchestration engine, no UI, no provider wiring). Worse, the path‑validation logic has a critical security bug (symlink escape not handled). The implementation is non‑functional.
- **Review** (Opus): Correctly rejects the build (score 28/100) and identifies the incompleteness and the symlink escape flaw. The review is thorough and actionable.

**Overall**, Pipeline A produced a strong plan and a valid critique, but the build is unusable. The plan and review add some value, but the core deliverable is missing. Score 25 reflects the partial credit for the plan and the helpful review.

#### Pipeline B
- **Plan** (DeepSeek): Adequate but shallow. It lists the main components (harness, scoped access, gateway, UI) but lacks the specifics seen in A. It omits important details like circuit breakers, symlink handling, provider interface signatures, dry‑run/staging areas, and budget exhaustion handling.
- **Build** (DeepSeek): Also incomplete. Only a React hook skeleton and state types are provided. No backend, no safety layer, no agent runtime. The code stops mid‑expression and is not functional. Critical requirements are completely unmet.
- **Review** (DeepSeek): Missing. The review section is empty, meaning no validation or improvement suggestions were generated.

**Overall**, Pipeline B lacks the thoroughness of A’s planning and has an equally incomplete build, with no self‑correcting review. Score 10 reflects the very limited attempt (only types and a hook stub) and the absence of a review.

### Discrepancies & Failures
- **Neither pipeline delivered a working build.** The task required a functional Cowork tab; both builds are truncated and omit all core logic.
- **Safety requirements were not met.** The only attempt at path validation (in A) has a symlink escape vulnerability; Pipeline B never reached that level.
- **Pipeline A benefited from a detailed plan and a stringent review**, exposing its own shortcomings. Pipeline B provided no such quality control.

### Value‑per‑Dollar Observations
- B is significantly cheaper ($0.007 vs $0.100) and achieves a higher score‑per‑dollar (1388 vs 251), but this is misleading because **both outputs are failures**. The higher ratio merely reflects that B spent almost no money to produce almost nothing, while A invested more and produced a better plan and a meaningful review. In a real project, neither would be accepted, and the apparent value metric is irrelevant when the output is unusable.

**Conclusion:** Pipeline A is marginally better because it offers a high‑quality plan and a useful review, even though the build failed. Pipeline B offers nothing beyond a basic sketch. Both fall far short of the task’s objective.

---

## Cost-Effectiveness Table

| Pipeline | Est. Cost | Value/Cost | Notes |
|----------|-----------|------------|-------|
| A (Opus->DeepSeek->Opus) | $0.099775 | 1002.3 | |
| B (Full DeepSeek) | $0.007206 | 13877.3 | |

**Ornith model:** ornith9b (self-host cost: $0.0003/1K tokens)

## Executive Recommendation

_See meta-reviews above for detailed analysis._