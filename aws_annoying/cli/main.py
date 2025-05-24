# flake8: noqa: F401
from __future__ import annotations

import aws_annoying.cli.ecs
import aws_annoying.cli.load_variables
import aws_annoying.cli.mfa
import aws_annoying.cli.session_manager
from aws_annoying.utils.debugger import input_as_args

# App with all commands registered
from .app import app

__all__ = ("app",)


def entrypoint() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    with input_as_args():
        entrypoint()
