from __future__ import annotations

from ._app import session_manager_app


@session_manager_app.command()
def start() -> None:
    """Start new session."""
    # TODO(lasuillard): To be implemented
