# Cowork Tab Implementation Plan

## 1. Agent Harness Core & Multi-Step Orchestration
- Build an agent execution loop supporting plan→act→observe cycles with configurable max-step limits, per-step timeouts, and abort/pause/resume controls surfaced to the UI.
- Define a tool/action interface (read file, write file, list dir, run command, search) with structured inputs/outputs, and a state machine tracking step history, intermediate artifacts, and a shared scratchpad/context window.
- Implement step persistence (resumable sessions, transcript logging) and emit progress events to the frontend for real-time streaming of agent reasoning and actions.

## 2. Scoped File Access & Allowlist Security Layer
- Implement a directory allowlist resolver that canonicalizes all paths, rejects traversal (`../`, symlinks escaping root), and enforces read/write scopes per workspace; deny-by-default outside allowlisted roots.
- Classify operations into safe (read, list, search) vs. destructive (overwrite, delete, move, shell exec) and gate destructive ops behind explicit user confirmation prompts with diff/preview where applicable.
- Add an audit log of every file operation (path, type, before/after hash) plus a dry-run/sandbox mode for previewing planned mutations before approval.

## 3. Provider-Pluggable Model Abstraction
- Reuse/extend the existing provider interface (shared with Chat/Code tabs) so Cowork can swap LLM backends via config; define capability metadata (tool-calling support, context size, streaming).
- Implement a tool-call normalization layer that maps provider-specific function-calling formats to the harness's internal action schema, with a fallback prompt-based parser for non-tool-call providers.

## 4. Spend-Guard Gateway & Cost Meter Integration
- Route all model calls through the shared spend-guard gateway, passing the Cowork tab/session as a cost-attribution dimension; enforce per-session and per-step budget caps that halt the agent when exceeded.
- Wire token/cost accounting into the shared cost meter so multi-step runs aggregate correctly, displaying live spend in the UI and pre-flight cost estimates before long agent runs.

## 5. UI, Wiring & Validation
- Build the Cowork tab UI: task input, live step/transcript view, confirmation modals for destructive actions, allowlist/directory picker, spend display, and run controls (start/stop/resume).
- Add config surface for selecting providers, setting budgets, and managing allowlisted directories; integrate with shared app state and auth/session context.
- Test coverage: unit tests for path-allowlist edge cases and confirmation gating, integration tests for multi-step runs against a mock provider, and spend-guard enforcement tests verifying budget halts and cost-meter accuracy.