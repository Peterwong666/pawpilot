# Security Policy

## Reporting a Vulnerability

Please **do not open a public GitHub issue** for security vulnerabilities.

Instead, report privately via GitHub's
[private vulnerability reporting](https://github.com/Peterwong666/pawpilot/security/advisories/new),
or contact the maintainer ([@Peterwong666](https://github.com/Peterwong666)) directly.
You can expect an acknowledgement within a few days.

## A Note on API Keys

- Never paste real API keys (`SILICONFLOW_API_KEY`, `DEEPSEEK_API_KEY`,
  `DASHSCOPE_API_KEY`, …) into issues, PRs, logs, or screenshots — redact them first.
- Keys belong in your local `.env` (git-ignored) or your deployment's secret store,
  never in source code.
- If you accidentally committed a key, rotate it immediately at the provider's
  console, then rewrite history or ask a maintainer for help.
