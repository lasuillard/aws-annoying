from __future__ import annotations

import os
import signal
from pathlib import Path  # noqa: TC003

import typer
from rich import print  # noqa: A004

from ._app import session_manager_app


@session_manager_app.command()
def stop(
    pid_file: Path = typer.Option(  # noqa: B008
        "./session-manager-plugin.pid",
        help="The path to the PID file to store the process ID of the session manager plugin.",
    ),
    remove: bool = typer.Option(  # noqa: FBT001
        True,  # noqa: FBT003
        help="Remove the PID file after stopping the session.",
    ),
) -> None:
    """Stop running session for PID file."""
    # Check if PID file exists
    if not pid_file.is_file():
        print(f"❌ PID file not found: {pid_file}")
        raise typer.Exit(1)

    # Read PID from file
    pid_content = pid_file.read_text()
    try:
        pid = int(pid_content)
    except ValueError:
        print(f"🚫 PID file content is invalid; expected integer, but got: {type(pid_content)}")
        raise typer.Exit(1) from None

    # Send SIGTERM to the process
    try:
        print(f"⚠️ Terminating running process with PID {pid}.")
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print(f"❗ Tried to terminate process with PID {pid} but does not exist.")

    # Remove the PID file
    if remove:
        print(f"✅ Removed the PID file {pid_file}.")
        pid_file.unlink()

    print("✅ Terminated the session successfully.")
