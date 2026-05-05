# Project rules

> Hard constraints. Violations should block commits or be flagged in review.

- Never commit secrets. PII must never reach the LLM.
- Tests are required for any new feature, fix, or refactor — same commit, no exceptions.
- Don't add a feature, abstraction, or fallback the task doesn't require.
- Don't introduce backwards-compatibility shims for code that hasn't shipped.

_(add project-specific rules below — they propagate to every AI tool on `dotagent sync`)_
