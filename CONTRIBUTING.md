# Contributing to PawPilot

Thanks for your interest in contributing!

## Workflow

1. **Fork & branch.** Create a feature branch from `main`
   (e.g. `feat/my-change` or `fix/my-bug`).
2. **Set up.** `uv sync` installs all dependencies (Python ≥ 3.12 required).
3. **Test.** Make sure the full suite is green before opening a PR:

   ```bash
   uv run pytest -q
   ```

   Tests are hermetic (mocked LLM/retriever) — no API keys or database needed.
4. **Lint.** Run `uv run ruff check app scripts tests web eval` and keep it clean.
5. **Open a PR.** Fill in the pull request template and describe the *why* of the
   change, not just the *what*.

## Guidelines

- Keep changes focused; one concern per PR.
- Never commit API keys or other secrets — configuration lives in `.env`
  (git-ignored); use `.env.example` as the template.
- User-facing UI strings go through `web/i18n.py` (zh + en).
