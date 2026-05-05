---
name: plan
description: Draft an implementation plan rooted in rules, architecture, and graduated patterns.
inputs: [task]
outputs: [plan]
---

# Plan

Plans must:
- Cite the architecture sections and semantic rules they assume.
- Identify files to touch, by path.
- Note which existing patterns (`memory/semantic/patterns/`) the plan is following or breaking.
- Include a verification step: how the user can confirm the change works.
