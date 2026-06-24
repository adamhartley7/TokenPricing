# TokenPricing

Neutral, fully-sourced cost comparison of LLM access options for a heavy Claude Code user
(June 2026): **DeepSeek API · Claude API · Gemini API · Claude Max 5x · Claude Max 20x**.

- **[REPORT.md](./REPORT.md)** — findings, 5-way price table, subscription-vs-API break-even math,
  Claude Code↔DeepSeek routing on Windows, and a privacy/jurisdiction section. Every figure cited.
- **`index.html`** — interactive cost calculator. Enter your monthly input/output token volumes
  (with cache-hit % and batch toggles) and see live monthly $ for each metered option, with the
  flat Max plans as reference lines plus a break-even readout.

**Live:** https://adamhartley7.github.io/TokenPricing/ — served via GitHub Pages from the
`claude/token-app-deepseek-cost-analysis-fvsql5` branch (root). Or open `index.html` locally in any
browser. (When you merge this branch into `main`, repoint Pages at `main` for a tidier setup.)

> Cost estimates only; not financial advice. Prices change — verify live before committing spend.
