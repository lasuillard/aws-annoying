from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
import typer
from rich import print  # noqa: A004

from .app import app

if TYPE_CHECKING:
    from collections.abc import Iterator

_DELETE_CHUNK_SIZE = 10


@app.command()
def ecs_task_definition_lifecycle(
    *,
    family: str = typer.Option(
        ...,
        help="The name of the task definition family.",
        show_default=False,
    ),
    keep_latest: int = typer.Option(
        ...,
        help="Number of latest (revision) task definitions to keep.",
        show_default=False,
        min=1,
        max=100,
    ),
    delete: bool = typer.Option(
        False,  # noqa: FBT003
        help="Delete the task definition after deregistering it.",
    ),
    dry_run: bool = typer.Option(
        False,  # noqa: FBT003
        help="Do not perform any changes, only show what would be done.",
    ),
) -> None:
    """Execute ECS task definition lifecycle."""
    if dry_run:
        print("⚠️ Dry run mode enabled. Will not perform any actual changes.")

    ecs = boto3.client("ecs")

    # Get all task definitions for the family
    response_iter = ecs.get_paginator("list_task_definitions").paginate(
        familyPrefix=family,
        status="ACTIVE",
        sort="ASC",
    )
    task_definition_arns = []
    for response in response_iter:
        task_definition_arns.extend(response["taskDefinitionArns"])

    # Sort by revision number
    task_definition_arns.sort(key=lambda arn: int(arn.split(":")[-1]))

    # Keep the latest N task definitions
    expired_taskdef_arns = task_definition_arns[:-keep_latest]
    print(f"⚠️ Deregistering {len(expired_taskdef_arns)} task definitions...")
    for arn in expired_taskdef_arns:
        if not dry_run:
            ecs.deregister_task_definition(taskDefinition=arn)

        # ARN like: "arn:aws:ecs:<region>:<account-id>:task-definition/<family>:<revision>"
        _, family_revision = arn.split(":task-definition/")
        print(f"✅ Deregistered task definition [yellow]{family_revision!r}[/yellow]")

    if delete and expired_taskdef_arns:
        # Delete the expired task definitions in chunks due to API limitation
        print(f"⚠️ Deleting {len(expired_taskdef_arns)} task definitions in chunks of size {_DELETE_CHUNK_SIZE}...")
        for idx, chunk in enumerate(_chunker(expired_taskdef_arns, _DELETE_CHUNK_SIZE)):
            if not dry_run:
                ecs.delete_task_definitions(taskDefinitions=chunk)

            print(f"✅ Deleted {len(chunk)} task definitions in {idx}-th batch.")


def _chunker(sequence: list, size: int) -> Iterator[list]:
    """Yield successive chunks of a given size from the sequence."""
    for i in range(0, len(sequence), size):
        yield sequence[i : i + size]
