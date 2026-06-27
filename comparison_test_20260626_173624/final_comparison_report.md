# Final Comparison Report
**Date:** 2026-06-26 17:57:58
**Task:** Build a Cowork tab for the 7C's app — a multi-step agent harness with scoped file access, allowlisted directories, no destructive ops without confirmation, and provider-pluggable, sharing the same spe

## Pipeline Summary

| Pipeline | Models | Plan Tokens | Build Tokens | Review Tokens | Est. Cost |
|----------|--------|-------------|--------------|---------------|-----------|
| A (Opus->DeepSeek->Opus) | claude-opus-4-8->deepseek-v4-pro->claude-opus-4-8 | 1101 | 4784 | 6612 | $0.102668 |
| B (Full DeepSeek) | deepseek-v4-pro->deepseek-v4-pro->deepseek-v4-pro | 1880 | 4771 | 3735 | $0.007951 |

---

## Meta-Review: Opus
# Evaluation of Two Pipelines

## Overview

Both pipelines attempted the same task (build a Cowork tab). Critically, **both produced truncated, incomplete code** and **both self-rejected** in their own review steps. The key differentiators are: depth/quality of what was produced, honesty of self-assessment, and cost.

---

## Pipeline A (Opus → DeepSeek → Opus)

### Detailed Reasoning
- **Plan (Opus):** Strong, well-structured plan covering all 5 workstreams: agent harness, scoped file access/allowlist, provider abstraction, spend-guard integration. Demonstrates genuine understanding of the security-critical aspects (path canonicalization, traversal rejection, symlink escapes, deny-by-default). The plan itself is truncated mid-section 4, but covers more ground meaningfully.
- **Build (DeepSeek):** Delivered partial code but with **higher technical quality** in what exists. The allowlist resolver shows real security awareness (`path.resolve` + `fs.realpath`, parent-dir validation for new files, belt-and-suspenders `path.relative` check). Zod schemas with runtime validation are a genuine defense. However, code cuts off mid-`fs.mkdir`; provider abstraction, spend-guard, agent loop, UI, and tests are all absent.
- **Review (Opus):** **Excellent, honest, critical review.** Correctly identifies truncation as a hard blocker, enumerates exactly which workstreams are missing, distinguishes the ~2 partially-covered areas from the 3+ entirely missing ones. Score of 38/100 is well-calibrated to reality.

### Strengths
- Higher-quality security primitives (the hardest, most error-prone part)
- Honest, surgical self-review with specific FIX-FIRST blockers
- Plan demonstrates deeper domain understanding

### Weaknesses
- Code still truncated and non-compilable
- Core deliverables (orchestration loop, provider plugin, spend-guard) absent
- ~10x more expensive

---

## Pipeline B (Full DeepSeek)

### Detailed Reasoning
- **Plan (DeepSeek):** Competent and covers the same workstreams, organized clearly. Slightly less depth on security specifics than A, but adequate. Also truncated.
- **Build (DeepSeek):** Produced mostly **scaffolding** — config file, type definitions (`ToolCall`, `StepState`, `ConfirmationRequest`, `CoworkSession`). These are reasonable types but represent **less actual functional code** than A. No working allowlist logic, no zod validation, no tool execution. The `scopedFS.ts` is also cut off. The claim "Below are the complete, ready-to-save files" is **directly contradicted** by the truncated, type-only output — a credibility problem.
- **Review (DeepSeek):** Honest and accurate — correctly self-assigns 20/100, identifies all missing pieces. Good integrity, but the review is essentially cataloguing a near-empty implementation.

### Strengths
- Honest self-review
- ~13x cheaper
- Type definitions are clean

### Weaknesses
- Produced mostly types/config, little functional logic
- Overclaimed completeness in build prose ("complete, ready-to-save files")
- Less security depth than A
- Still truncated

---

## Cost & Value Analysis

| Pipeline | Cost | Self-Score | Adjusted Quality* | Value/Dollar (adj. score/$) |
|----------|------|-----------|-------------------|------------------------------|
| A (Opus→DeepSeek→Opus) | $0.102668 | 38/100 | ~38 | ~370 |
| B (Full DeepSeek) | $0.007951 | 20/100 | ~22 | ~2,767 |

\*Adjusted quality is my independent assessment, roughly aligning with their self-scores, which I judge well-calibrated.

---

## Comparison Table

| Dimension | Pipeline A | Pipeline B |
|-----------|-----------|-----------|
| Plan quality | Stronger (deeper security/arch detail) | Solid, slightly shallower |
| Build completeness | Partial; ~2 of 5 areas | Mostly types/scaffolding |
| Code quality (of what exists) | Higher (real allowlist hardening, zod) | Lower (types only) |
| Functional logic delivered | Some (security layer, tool schemas) | Minimal |
| Review honesty | Excellent, surgical | Good, accurate |
| Overclaiming | None | Yes ("complete files") |
| Compilable? | No (truncated) | No (truncated) |
| Cost | $0.1027 | $0.0080 |
| Self-score | 38/100 | 20/100 |
| My independent score | **40/100** | **22/100** |
| Value/dollar | ~370 | ~2,767 |

---

## Verdict

**Neither pipeline succeeded** — both failed to deliver a working, complete Cowork tab, and both were truncated. As deliverables, both are rejections.

- **Higher absolute quality: Pipeline A.** It produced more genuinely useful, security-conscious code, a deeper plan, and an outstanding critical review. If the goal is the best artifact, A wins.

- **Higher value-per-dollar: Pipeline B by ~7.5x.** Despite lower quality, it cost ~13x less while producing ~55% of A's quality score. For exploratory/draft work where cost matters, B is more efficient.

**Recommendation:** Both pipelines reveal a systemic problem — **output truncation** (likely token-limit driven). Neither is shippable. A is preferable when correctness/security matter (the right call for this security-sensitive task with destructive ops and file access), since B's type-only scaffolding leaves the riskiest logic entirely unwritten. The premium for A is justified *only if* the truncation issue is fixed; otherwise both waste spend on incomplete work.

**Key cross-pipeline note:** Both review steps were honest and well-calibrated — a positive signal. The most actionable fix for both is increasing output budget / chunking the build so code isn't cut off mid-function.

---

## Meta-Review: DeepSeek
## Pipeline Comparison

Both pipelines **failed to deliver a complete, working Cowork tab**. The task required a functional agent harness with scoped file access, confirmation gating, provider pluggability, and spend‑guard integration. Neither produced a compilable, coherent system; the core components (agent loop, provider abstraction, cost integration, UI, tests) are absent from both. The scoring reflects **the value of what was produced relative to the full specification**.

| Pipeline | Score (out of 100) | Cost (USD) | Value‑per‑Dollar (score / cost) | Strengths | Weaknesses |
|----------|-------------------|------------|--------------------------------|-----------|------------|
| **A** (Opus → DeepSeek → Opus) | **35** | $0.102668 | **340.9** | • Detailed, requirement‑aligned plan<br>• Partial security layer is well‑designed: zod schemas, canonicalization, realpath, audit hashing, safe/destructive classification, promise‑based confirmation gating<br>• Review is precise and correctly rejects the incomplete output | • Code is truncated mid‑statement – non‑compilable<br>• Entire agent engine, provider abstraction, spend‑guard wiring, UI, and tests are **missing**<br>• No working multi‑step loop or tool executor<br>• Only ~40% of the security module was attempted |
| **B** (Full DeepSeek) | **20** | $0.007951 | **2515.7** | • Clean configuration and typed contracts (session, tool call, step state)<br>• Extremely low cost | • **No agent engine** – missing the core loop, planning, observation<br>• **No tool implementations** – only stub types, no scoped FS logic beyond an incomplete `scopedFS.ts`<br>• **No confirmation mechanism** – the `requiresConfirmation` flag is never acted upon<br>• **No spend‑guard or cost meter integration** – only a static `totalCost` field in the session type<br>• **No UI, API routes, or tests**<br>• Build is essentially a skeleton with no executable behaviour |

### Reasoning Behind Scores

**Pipeline A** delivered a stronger plan and a more advanced – albeit partial – implementation of the security layer. The code showed real architectural thinking (e.g., canonicalising paths, parent‑directory validation for writes to non‑existent files, hash‑based audit logging). However, the build is undeniably incomplete and was **rejected by its own reviewer (38/100 on the build segment)**. Factoring in the absence of every other major workstream, a holistic score of **35/100** reflects a well‑started but profoundly unfinished submission.

**Pipeline B** contributed only schema‑level structure and a few environment‑based config items. The plan is less specific, and the build is essentially a set of type declarations plus an incomplete file‑system stub. No meaningful behaviour is implemented. Its own review judged it **20/100**, which aligns with my assessment. The enormous value‑per‑dollar figure is misleading; it arises solely from the sub‑cent cost, not from delivered quality.

### Verdict

Neither pipeline comes close to satisfying the task. Pipeline A is marginally preferable because it at least attempted a sophisticated security foundation and provided a thorough plan, whereas Pipeline B is almost entirely empty. In a real‑world setting, both would be returned for a complete rewrite.

---

## Cost-Effectiveness Table

| Pipeline | Est. Cost | Value/Cost | Notes |
|----------|-----------|------------|-------|
| A (Opus->DeepSeek->Opus) | $0.102668 | 974.0 | |
| B (Full DeepSeek) | $0.007951 | 12577.0 | |

**Ornith model:** ornith9b (self-host cost: $0.0003/1K tokens)

## Executive Recommendation

_See meta-reviews above for detailed analysis._