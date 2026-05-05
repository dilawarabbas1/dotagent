# Git Proxy

Wraps `git` so every commit is captured into episodic memory. Optionally rejects commits violating `rules.md`. Annotates commit trailers with `Co-authored-by: dotagent <tool=...,actor=...>` so attribution survives in `git log`.

Installed as `pre-commit` and `post-commit` hooks by `dotagent init` / `dotagent sync`.
