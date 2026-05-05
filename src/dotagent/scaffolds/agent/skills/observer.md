---
name: observer
description: Passively records work events into episodic memory and keeps working memory current.
inputs: [event]
outputs: [episodic_event_id]
---

# Observer

Runs on every session start, every commit, every test run, every error. Records:

- `kind`, `actor`, `tool`, `host`, `session`, `ts`
- For commits: `branch`, `files`, `diff_sha`, `summary`
- For errors / reverts: signature + context

Working memory holds the live session's "what's happening now" — files in scope, goal, blockers — and rolls forward across tool calls.
