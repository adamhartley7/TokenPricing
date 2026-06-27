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