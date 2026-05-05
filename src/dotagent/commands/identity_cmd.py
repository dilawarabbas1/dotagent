from __future__ import annotations

import click

from ..identity import Identity, load_user_identity, resolve, save_user_identity
from ..paths import find_repo_root


@click.command("show", help="Show the current actor identity.")
def identity_show() -> None:
    user = load_user_identity()
    if user:
        click.echo(f"id:     {user.id}")
        click.echo(f"name:   {user.name}")
        click.echo(f"emails: {', '.join(user.emails) or '(none)'}")
        click.echo(f"tool:   {user.default_tool}")
        return
    detected = resolve(find_repo_root())
    click.echo("(no saved identity; falling back to git config)")
    click.echo(f"id:     {detected.id}")
    click.echo(f"name:   {detected.name}")
    click.echo(f"emails: {', '.join(detected.emails) or '(none)'}")


@click.command("set", help="Save your identity (used across all dotagent projects).")
@click.option("--id", "id_", help="Stable id (e.g., alice).")
@click.option("--name", help="Display name.")
@click.option("--email", "emails", multiple=True, help="One or more emails.")
@click.option("--tool", help="Default AI tool (claude_code | cursor | copilot | opencode).")
def identity_set(id_, name, emails, tool) -> None:
    cur = load_user_identity()
    if cur is None:
        cur = resolve(find_repo_root())
    new = Identity(
        id=id_ or cur.id,
        name=name or cur.name,
        emails=list(emails) or cur.emails,
        default_tool=tool or cur.default_tool,
        github=cur.github,
        gitlab=cur.gitlab,
        role=cur.role,
    )
    save_user_identity(new)
    click.echo(f"saved → {new.id} <{', '.join(new.emails) or 'no email'}>")
