- **Extend shared gateway & provider abstraction**  
  Build provider-pluggable agent backends that reuse the same LLM gateway, spend‑guard rate limiting, and real‑time cost meter already powering the Chat and Code tabs. Define a uniform interface for token counting and budget enforcement; any model (OpenAI, Anthropic, etc.) can be swapped via configuration so the Cowork tab instantly benefits from existing usage controls and billing.

- **Implement scoped file sandbox with user‑confirmation**  
  Create a file‑access middleware that restricts all reads/writes to an approved set of allowlisted directories. Insert a mandatory confirmation gate before any destructive operation (write, delete, rename, move): the agent harness yields a pending action, the UI prompts the user, and execution proceeds only after explicit approval. This middleware is wired into every tool call that touches the filesystem.

- **Build the multi‑step agent harness**  
  Develop a state‑machine agent loop that decomposes tasks, selects tools, performs scoped file ops, observes results, and iterates. Include error recovery, timeouts, and user‑input pauses (especially for confirmations). Make the loop provider‑agnostic by using the abstraction from step 1, and allow reuse of the Code tab’s executor under the same directory restrictions.

- **Develop the Cowork tab UI**  
  Implement a chat‑centric or split‑pane interface that visualises each step of the agent’s plan, tool calls, and results. Embed inline confirmation dialogs for destructive actions and a directory‑scope indicator. Wire the UI to the agent harness and the shared cost meter, so all spend is tracked in the same footer or sidebar as Chat and Code.