from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import boto3
import pytest
from typer.testing import CliRunner

from aws_annoying.main import app

from ._helpers import normalize_console_output, repeat_options

if TYPE_CHECKING:
    from pytest_snapshot.plugin import Snapshot

    from tests.conftest import Invoker

# * Command `load-variables` cannot use Typer CLI runner because it uses `os.execvpe` internally,
# * which replaces the current process with the new one, breaking pytest runtime.
# * But tests that does not reach the `os.execvpe` statement can use Typer CLI runner (or provide `--no-replace` flag).
runner = CliRunner()


def setup_resources(*, env_base: dict[str, str] | None = None) -> dict[str, Any]:
    """Set up AWS resources."""
    _variables: dict[Literal["secrets", "parameters"], dict[str, Any]] = {
        "secrets": {
            # Pass to CLI arguments
            "my-app/django-sensitive-settings": {
                "DJANGO_SECRET_KEY": "my-secret-key",
            },
        },
        "parameters": {
            # Pass to CLI arguments
            "/my-app/django-settings": {
                "DJANGO_SETTINGS_MODULE": "config.settings.local",
                "DJANGO_ALLOWED_HOSTS": "*",
                "DJANGO_DEBUG": "False",
            },
            # Pass to execution environment
            "/my-app/override": {
                "DJANGO_ALLOWED_HOSTS": "127.0.0.1,192.168.0.2",
            },
        },
    }

    # Secrets
    secretsmanager = boto3.client("secretsmanager")
    secrets = {}
    for name, value in _variables["secrets"].items():
        secret = secretsmanager.create_secret(
            Name=name,
            SecretString=json.dumps(value),
        )
        secrets[name] = {"data": value, "resource": secret}

    # Parameters
    ssm = boto3.client("ssm")
    parameters = {}
    for name, value in _variables["parameters"].items():
        ssm.put_parameter(
            Name=name,
            Value=json.dumps(value),
            Type="String",
        )
        parameter = ssm.get_parameter(Name=name)["Parameter"]
        parameters[name] = {"data": value, "resource": parameter}

    env = env_base or os.environ | {
        # Direct environment variables
        "LOAD_AWS_CONFIG__900_override": parameters["/my-app/override"]["resource"]["ARN"],
        "DJANGO_SETTINGS_MODULE": "config.settings.development",
    }
    load_resources = [
        secrets["my-app/django-sensitive-settings"]["resource"]["ARN"],
        parameters["/my-app/django-settings"]["resource"]["ARN"],
    ]

    return {
        # Test environment
        "env": env,
        "load_resources": load_resources,
        # Resources
        "secrets": {k: v["resource"]["ARN"] for k, v in secrets.items()},
        "parameters": {k: v["resource"]["ARN"] for k, v in parameters.items()},
    }


printenv_py = str(Path(__file__).parent / "_helpers" / "scripts" / "printenv.py")
printenv = [printenv_py, "DJANGO_SETTINGS_MODULE", "DJANGO_SECRET_KEY", "DJANGO_DEBUG", "DJANGO_ALLOWED_HOSTS"]


def test_nothing(snapshot: Snapshot) -> None:
    """If nothing is provided, the command should do nothing."""
    # Arrange
    # ...

    # Act
    result = runner.invoke(
        app,
        [
            "load-variables",
        ],
    )

    # Assert
    assert result.exit_code == 0
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")


def test_unsupported_resource(snapshot: Snapshot) -> None:
    """If unsupported resource ARN provided, should exit with error."""
    # Arrange
    # ...

    # Act
    result = runner.invoke(
        app,
        [
            "load-variables",
            "--arns",
            "arn:aws:s3:::my-bucket/my-object",
            printenv_py,
        ],
    )

    # Assert
    assert result.exit_code == 1
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")


def test_basic(snapshot: Snapshot, invoke_cli: Invoker) -> None:
    """Test basic usage."""
    # Arrange
    setup = setup_resources()

    # Act
    result = invoke_cli(
        "load-variables",
        *repeat_options("--arns", setup["load_resources"]),
        "--no-replace",
        "--",
        *printenv,
        env=setup["env"],
    )

    # Assert
    assert result.returncode == 0
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")
    assert result.stderr == ""


def test_replace_quiet(snapshot: Snapshot, invoke_cli: Invoker) -> None:
    """Test the most common practical use-case."""
    # Arrange
    setup = setup_resources()

    # Act
    result = invoke_cli(
        "load-variables",
        *repeat_options("--arns", setup["load_resources"]),
        "--env-prefix",
        "LOAD_AWS_CONFIG__",
        "--quiet",
        "--",
        *printenv,
        env=setup["env"],
    )

    # Assert
    assert result.returncode == 0
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")
    assert result.stderr == ""


def test_env_prefix(snapshot: Snapshot, invoke_cli: Invoker) -> None:
    """Test prefixed environment variables support."""
    # Arrange
    setup = setup_resources()

    # Act
    result = invoke_cli(
        "load-variables",
        *repeat_options("--arns", setup["load_resources"]),
        "--env-prefix",
        "LOAD_AWS_CONFIG__",
        "--no-replace",
        "--",
        *printenv,
        env=setup["env"],
    )

    # Assert
    assert result.returncode == 0
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")
    assert result.stderr == ""


def test_dry_run(snapshot: Snapshot, invoke_cli: Invoker) -> None:
    """If dry-run mode enabled, it shouldn't load variables."""
    # Arrange
    setup = setup_resources()

    # Act
    result = invoke_cli(
        "load-variables",
        *repeat_options("--arns", setup["load_resources"]),
        "--env-prefix",
        "LOAD_AWS_CONFIG__",
        "--no-replace",
        "--dry-run",
        "--",
        *printenv,
        env=setup["env"],
    )

    # Assert
    assert result.returncode == 0
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")
    assert result.stderr == ""


def test_overwrite_env(snapshot: Snapshot, invoke_cli: Invoker) -> None:
    """Test `--overwrite-env` flag. If provided, it should overwrite the existing environment variables."""
    # Arrange
    setup = setup_resources()

    # Act
    result = invoke_cli(
        "load-variables",
        *repeat_options("--arns", setup["load_resources"]),
        "--env-prefix",
        "LOAD_AWS_CONFIG__",
        "--no-replace",
        "--overwrite-env",
        "--",
        *printenv,
        env=setup["env"],
    )

    # Assert
    assert result.returncode == 0
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")
    assert result.stderr == ""


@pytest.mark.parametrize(
    argnames="arn",
    argvalues=[
        # TODO(lasuillard): Moto Secrets Manager does not respond with error for non-existing resources
        # "arn:aws:secretsmanager:us-east-1:123456789012:secret:unknown-secret", # noqa: ERA001;
        "arn:aws:ssm:us-east-1:123456789012:parameter/unknown-parameter",
    ],
    ids=[
        # "secretsmanager",
        "ssm",
    ],
)
def test_resource_not_found(snapshot: Snapshot, invoke_cli: Invoker, arn: str) -> None:
    """Test with resource does not exists."""
    # Arrange
    setup = setup_resources()

    # Act
    result = invoke_cli(
        "load-variables",
        *repeat_options("--arns", setup["load_resources"]),
        "--arns",
        arn,
        "--no-replace",
        "--",
        *printenv,
        env=setup["env"],
    )

    # Assert
    assert result.returncode == 1
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")
    assert result.stderr == ""
