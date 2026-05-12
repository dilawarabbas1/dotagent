from __future__ import annotations

import click

from .commands.context_cmd import context
from .commands.doctor_cmd import doctor
from .commands.dream_cmd import dream_group
from .commands.identity_cmd import identity_set, identity_show
from .commands.init_cmd import init
from .commands.migrate_cmd import migrate_cco
from .commands.observe_cmd import observe
from .commands.reindex_cmd import reindex
from .commands.serve_cmd import serve
from .commands.skill_cmd import skill_group
from .commands.status_cmd import status
from .commands.sync_cmd import sync
from .commands.tool_cmd import tool_group
from .commands.trailer_cmd import trailer
from .commands.watch_cmd import watch_group
from .commands.visibility_cmd import (
    activity,
    feed,
    leaderboard,
    reindex_events,
    timeline,
    who,
)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="dotagent")
def main() -> None:
    """dotagent — one source of truth, every AI coding tool in sync."""


@main.group(help="Identity management.")
def identity() -> None:
    pass


identity.add_command(identity_show)
identity.add_command(identity_set)

# core
main.add_command(init)
main.add_command(sync)
main.add_command(status)
main.add_command(observe)
main.add_command(reindex)
main.add_command(context)
main.add_command(trailer)
main.add_command(doctor)
main.add_command(migrate_cco, name="migrate-cco")

# Phase 2: visibility
main.add_command(who)
main.add_command(activity)
main.add_command(timeline)
main.add_command(feed)
main.add_command(leaderboard)
main.add_command(reindex_events)

# Phase 3: skills
main.add_command(skill_group)

# Phase 4: tools
main.add_command(tool_group)

# Phase 5: dream
main.add_command(dream_group)

# Beyond Phase 6: watcher + server
main.add_command(watch_group)
main.add_command(serve)


if __name__ == "__main__":
    main()
