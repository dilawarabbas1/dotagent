"""Optional centralized event server for teams.

Install: `pip install dotagent[server]`. Run: `dotagent serve --host 0.0.0.0 --port 9700`.
"""

from .app import build_app

__all__ = ["build_app"]
