from __future__ import annotations

import os
import secrets

import click


@click.command(name="serve", help="Run the centralized event server (requires `pip install dotagent[server]`).")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=9700, type=int)
@click.option("--db", "db_path", default=os.path.expanduser("~/.local/share/dotagent/server.sqlite"))
@click.option("--bootstrap-admin-token", default=None,
              help="Pre-seed an admin token (printed if omitted).")
def serve(host: str, port: int, db_path: str, bootstrap_admin_token: str | None) -> None:
    try:
        import uvicorn
    except ImportError as e:
        raise click.ClickException("server extras not installed — run `pip install 'dotagent[server]'`") from e
    from ..server import build_app

    if not bootstrap_admin_token:
        bootstrap_admin_token = secrets.token_urlsafe(24)
        click.echo(f"[bootstrap] admin token: {bootstrap_admin_token}")
        click.echo(f"            store it; create scoped tokens via POST /tokens")

    app = build_app(db_path=db_path, bootstrap_admin_token=bootstrap_admin_token)
    click.echo(f"dotagent server → http://{host}:{port}  db={db_path}")
    uvicorn.run(app, host=host, port=port, log_level="info")
