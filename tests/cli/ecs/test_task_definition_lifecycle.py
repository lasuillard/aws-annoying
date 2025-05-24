from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
import pytest
from typer.testing import CliRunner

from aws_annoying.cli.main import app
from tests.cli._helpers import normalize_console_output

if TYPE_CHECKING:
    from pytest_snapshot.plugin import Snapshot

runner = CliRunner()

pytestmark = [
    pytest.mark.unit,
    pytest.mark.usefixtures("use_moto"),
]


def test_basic(snapshot: Snapshot) -> None:
    """The command should deregister the oldest task definitions."""
    # Arrange
    ecs = boto3.client("ecs")
    family = "my-task"
    num_task_defs = 25
    for i in range(1, num_task_defs + 1):
        ecs.register_task_definition(
            family=family,
            containerDefinitions=[
                {
                    "name": "my-container",
                    "image": f"my-image:{i}",
                    "cpu": 0,
                    "memory": 0,
                },
            ],
        )

    # Act
    keep_latest = 10
    result = runner.invoke(
        app,
        [
            "ecs",
            "task-definition-lifecycle",
            "--family",
            family,
            "--keep-latest",
            str(keep_latest),
        ],
    )
    task_definitions = [
        ecs.describe_task_definition(taskDefinition=f"{family}:{i}")["taskDefinition"]
        for i in range(1, num_task_defs + 1)
    ]

    # Assert
    assert result.exit_code == 0
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")

    # ?: Moto (v5.1.1) `ecs.list_task_definitions` does not handle `status` filter properly
    # ?:               + sorting also does not work (current behavior is ASC)
    assert [td["revision"] for td in task_definitions if td["status"] == "INACTIVE"] == list(
        range(1, num_task_defs - keep_latest + 1),  # 1..15
    )
    assert [td["revision"] for td in task_definitions if td["status"] == "ACTIVE"] == list(
        range(num_task_defs - keep_latest + 1, num_task_defs + 1),  # 16..25
    )


def test_dry_run(snapshot: Snapshot) -> None:
    """If `--dry-run` option given, the command should not perform any changes."""
    # Arrange
    ecs = boto3.client("ecs")
    family = "my-task"
    num_task_defs = 25
    for i in range(1, num_task_defs + 1):
        ecs.register_task_definition(
            family=family,
            containerDefinitions=[
                {
                    "name": "my-container",
                    "image": f"my-image:{i}",
                    "cpu": 0,
                    "memory": 0,
                },
            ],
        )

    # Act
    keep_latest = 10
    result = runner.invoke(
        app,
        [
            "--dry-run",
            "ecs",
            "task-definition-lifecycle",
            "--family",
            family,
            "--keep-latest",
            str(keep_latest),
        ],
    )
    task_definitions = [
        ecs.describe_task_definition(taskDefinition=f"{family}:{i}")["taskDefinition"]
        for i in range(1, num_task_defs + 1)
    ]

    # Assert
    assert result.exit_code == 0
    snapshot.assert_match(normalize_console_output(result.stdout), "stdout.txt")

    # ?: Moto (v5.1.1) `ecs.list_task_definitions` does not handle `status` filter properly
    # ?:               + sorting also does not work (current behavior is ASC)
    assert [td["revision"] for td in task_definitions if td["status"] == "INACTIVE"] == []
    assert len([td["revision"] for td in task_definitions if td["status"] == "ACTIVE"]) == num_task_defs
