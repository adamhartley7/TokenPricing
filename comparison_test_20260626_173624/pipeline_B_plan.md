1. **Architecture and Shared Infrastructure Setup**  
   - Add a new Cowork tab component to the 7C’s app, inheriting the existing spend-guard gateway, cost meter, and authentication services used by the Chat and Code tabs.  
   - Design the agent harness as a multi-step state machine with a tool dispatcher and a scoped file system adapter that enforces allowlisted directories.  
   - Abstract LLM provider calls behind a common interface that plugs into the shared provider gateway, allowing the Cowork tab to use any configured provider with consistent cost tracking and rate limiting.

2. **Scoped File Access and Safety Controls**  
   - Build a virtual file system middleware that intercepts all file operations (read/write/delete/list) and restricts them to a configurable set of allowed directories.  
   - Integrate this layer into the agent’s toolset so that every file-accessing tool automatically respects the allowlist.  
   - For any destructive operation (deletions, writes outside allowed scope, or modifications to existing files), display a confirmation dialog detailing the action and require explicit user approval before execution.

3. **Multi-Step Agent Engine and Tool Execution**  
   - Implement the agent loop: receive user prompt → plan steps → execute tools (scoped) → observe results → iterate, with a configurable step limit and cancel/abort capability.  
   - Define and register tools (file operations, code analysis, etc.) that route through the scoped file system and confirmation system.  
   - Build a step-by-step progress view in the UI that shows each tool call, its outcome, any pending confirmations, and the real‑time cost meter data pulled from the shared gateway.

4. **Integration with Spending Guard and Cost Metering**  
   - Wire the Cowork tab’s LLM calls through the same spend‑guard middleware that enforces budgets and rate limits for Chat and Code tabs.  
   - Display cost accumulation in the Cowork tab’s UI using the shared cost meter component, ensuring it reflects the same provider pricing and user budget.  
   - Verify that switching providers updates cost estimates and draws from the unified spend pool without disrupting other tabs.

5. **Testing, Configuration, and Rollout**  
   - Create comprehensive tests: scoped file system enforcement, destructive‑op confirmation flow, multi‑step agent loops, provider pluggability, and cross‑tab cost consistency.  
   - Expose configuration options (allowed directories, max steps, enabled providers) via app settings and validate through integration tests.  
   - Polish the UI to match the 7C’s design system, conduct user testing on realistic multi‑step tasks, and release the Cowork tab alongside documentation for its scoped access and confirmation features.