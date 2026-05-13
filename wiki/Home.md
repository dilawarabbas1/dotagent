# dotagent Wiki

> **One `.agent/` folder. Every AI coding tool in sync.**
> Bug registry, anti-patterns, DB hotspots, Redis keys, dependency map — every
> AI agent on your team reads the same canonical context, ranked by severity,
> every session, automatically.

Welcome. This wiki is the operational manual. For the code, see the
[main repo](https://github.com/dilawarabbas1/dotagent).

## Start here

- **[[Getting Started]]** — install in 30 seconds, first sync, first commit
- **[[Architecture]]** — the diagram, the four memories, how everything fits
- **[[Sources and Docs]]** — how `docs/*.md` becomes the source of truth

## Reference

- **[[Commands Reference]]** — every CLI command
- **[[Configuration Reference]]** — every key in `.agent/config.yaml`
- **[[Memory Model]]** — deep dive on Working / Episodic / Semantic / Personal

## Features

- **[[Auto-Dream]]** — the agent-learning loop with mandatory rationale
- **[[Server and RBAC]]** — centralized event server for teams
- **[[Multi-Project and Multi-Developer]]** — running on N repos with N teammates

## Migration & support

- **[[Migrating from Claude-Code-Optimization]]** — lossless migrator
- **[[Troubleshooting]]** — `dotagent doctor`, common issues, debug logging
- **[[FAQ]]** — answers to questions that come up

## Quick reference

```bash
# install (one machine, once)
pipx install "git+https://github.com/dilawarabbas1/dotagent"

# initialize a project (each repo, once)
cd ~/code/your-project
dotagent init               # zero prompts
dotagent doctor             # self-check
git add .agent/ CLAUDE.md && git commit -m "chore: add dotagent context"

# daily flow
dotagent sync               # after editing docs/ or .agent/*.md
dotagent context            # see exactly what an AI agent sees
dotagent who --file path/to/file.py    # which dev / AI touched it
dotagent dream run          # extract learning signals
```

## Status

**v0.2.0** — launch-ready. 79+ tests passing across all phases. See the
[CHANGELOG](https://github.com/dilawarabbas1/dotagent/blob/main/CHANGELOG.md).
