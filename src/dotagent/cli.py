from __future__ import annotations

import click

from .commands.context_cmd import context
from .commands.identity_cmd import identity_set, identity_show
from .commands.init_cmd import init
from .commands.observe_cmd import observe
from .commands.reindex_cmd import reindex
from .commands.status_cmd import status
from .commands.sync_cmd import sync


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="dotagent")
def main() -> None:
    """dotagent — one source of truth, every AI coding tool in sync."""


@main.group(help="Identity management.")
def identity() -> None:
    pass


identity.add_command(identity_show)
identity.add_command(identity_set)

main.add_command(init)
main.add_command(sync)
main.add_command(status)
main.add_command(observe)
main.add_command(reindex)
main.add_command(context)


if __name__ == "__main__":
    main()
