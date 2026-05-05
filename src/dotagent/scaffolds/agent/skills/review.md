---
name: review
description: Diff a proposed change against rules + patterns; surface violations and graduation candidates.
inputs: [diff]
outputs: [report, dream_candidates]
---

# Review

Output:
- ❌ rule violations (blocking)
- ⚠ pattern divergences (warning)
- ✅ patterns followed
- 🌱 candidate signals for Auto-Dream (recurring shapes worth graduating)
