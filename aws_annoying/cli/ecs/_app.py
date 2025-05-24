import typer

from aws_annoying.cli.app import app

ecs_app = typer.Typer(
    no_args_is_help=True,
    help="ECS (Elastic Container Service) utility commands.",
)
app.add_typer(ecs_app, name="ecs")
