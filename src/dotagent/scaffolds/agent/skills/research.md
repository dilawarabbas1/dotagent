---
name: research
description: Look up prior context across semantic memory, episodic memory, and the repo.
inputs: [question]
outputs: [brief]
---

# Research

When asked a question, walk:
1. Semantic memory (`memory/semantic/`) for relevant rules + patterns.
2. Episodic memory (`memory/episodic/`) for prior incidents touching the same files / topic.
3. The repo itself (grep, code-search) for ground truth.

Return a brief that cites file paths + episodic event IDs. Never invent.
