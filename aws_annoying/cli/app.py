from __future__ import annotations

import logging
import logging.config

import typer
from rich.console import Console

app = typer.Typer(
    pretty_exceptions_short=True,
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)


@app.callback()
def main(  # noqa: D103
    ctx: typer.Context,
    *,
    quiet: bool = typer.Option(
        False,  # noqa: FBT003
        help="Disable outputs.",
    ),
    verbose: bool = typer.Option(
        False,  # noqa: FBT003
        help="Enable verbose outputs.",
    ),
    dry_run: bool = typer.Option(
        False,  # noqa: FBT003
        help="Enable dry-run mode. If enabled, certain commands will avoid making changes.",
    ),
) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    console = Console(soft_wrap=True, emoji=False)
    logging_config: logging.config._DictConfigArgs = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "rich": {
                "format": "%(message)s",
                "datefmt": "[%X]",
            },
        },
        "handlers": {
            "null": {
                "class": "logging.NullHandler",
            },
            "rich": {
                "class": "aws_annoying.cli.logging_handler.RichLogHandler",
                "formatter": "rich",
                "console": console,
            },
        },
        "root": {
            "handlers": ["null"],
        },
        "loggers": {
            "aws_annoying": {
                "level": log_level,
                "handlers": ["rich"],
                "propagate": True,
            },
        },
    }
    if quiet:
        logging_config["loggers"]["aws_annoying"]["level"] = logging.CRITICAL

    logging.config.dictConfig(logging_config)

    # Global flags
    ctx.meta["dry_run"] = dry_run
