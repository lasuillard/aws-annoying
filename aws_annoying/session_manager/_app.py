import typer

from aws_annoying.app import app

session_manager_app = typer.Typer(
    no_args_is_help=True,
    help="AWS Session Manager CLI utilities.",
)
app.add_typer(session_manager_app, name="session-manager")
