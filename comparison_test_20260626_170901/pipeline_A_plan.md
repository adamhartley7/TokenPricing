# Implementation Plan: Cowork Tab for 7C's App

## 1. Agent Harness Core & Multi-Step Orchestration
- Design a step-based execution engine that decomposes tasks into discrete, observable steps (plan → act → observe → reflect loop), with per-step state persistence enabling pause/resume and rollback.
- Implement an event/transcript log capturing each step's tool calls, file operations, provider responses, and costs for auditability and UI streaming.
- Define a tool/action registry (file read/write/edit, shell, search) with declarative schemas, and enforce a max-step/iteration budget with circuit breakers to prevent runaway loops.

## 2. Scoped File Access & Safety Guardrails
- Build a sandboxed filesystem layer that resolves all paths against an **allowlisted directory** config, rejecting traversal (`../`), symlinks escaping the scope, and absolute paths outside bounds.
- Classify operations into read / non-destructive write / **destructive** (delete, overwrite, mass-edit, shell with side effects); require explicit user confirmation (with diff preview) before any destructive op executes.
- Add a dry-run/preview mode and a transactional staging area so changes can be reviewed and reverted as a unit before commit.

## 3. Provider-Pluggable Layer + Shared Spend-Guard & Cost Meter
- Reuse the existing provider abstraction from Chat/Code tabs; ensure Cowork routes all model calls through the **same spend-guard gateway** (rate limits, budget caps, kill-switch) and **shared cost meter** so spend aggregates across tabs.
- Implement per-session and per-step cost attribution, surfacing live token/cost telemetry to the harness so budget exhaustion gracefully halts the agent mid-task.
- Validate provider hot-swapping mid-session and confirm fallback/retry policies are consistent with existing tabs.

## 4. UI/UX — Cowork Tab Frontend
- Build the tab shell mirroring Chat/Code conventions: task input, live step timeline, streaming transcript, file-change diffs, and confirmation modals for destructive actions and directory-scope grants.
- Add controls for allowlist management (add/remove directories), provider selection, budget display, and run controls (start, pause, abort, approve-step).
- Surface cost meter inline and persist session history for resume/replay.

## 5. Integration, Testing & Rollout
- Write unit tests for path-scoping/allowlist enforcement and destructive-op gating; integration tests for the multi-step loop and spend-guard halting behavior; E2E tests covering full agent runs with confirmations.
- Add adversarial/security tests (path traversal, scope escape, budget-bypass attempts) and verify shared cost-meter accuracy against Chat/Code.
- Ship behind a feature flag with telemetry, staged rollout, and documentation for allowlist setup and safety model.