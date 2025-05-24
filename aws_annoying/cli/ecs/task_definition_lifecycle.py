from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import boto3
import typer

from ._app import ecs_app

if TYPE_CHECKING:
    from collections.abc import Iterator


logger = logging.getLogger(__name__)

# TODO(lasuillard): Support it as an option (e.g. `--config-section`)
_DELETE_CHUNK_SIZE = 10


@ecs_app.command()
def task_definition_lifecycle(
    ctx: typer.Context,
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
) -> None:
    """Execute ECS task definition lifecycle."""
    dry_run = ctx.meta["dry_run"]
    if dry_run:
        logger.info("Dry run mode enabled. Will not perform any actual changes.")

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
    logger.warning("Deregistering %d task definitions...", len(expired_taskdef_arns))
    for arn in expired_taskdef_arns:
        if not dry_run:
            ecs.deregister_task_definition(taskDefinition=arn)

        # ARN like: "arn:aws:ecs:<region>:<account-id>:task-definition/<family>:<revision>"
        _, family_revision = arn.split(":task-definition/")
        logger.warning("Deregistered task definition [yellow]%r[/yellow]", family_revision)

    if delete and expired_taskdef_arns:
        # Delete the expired task definitions in chunks due to API limitation
        logger.warning(
            "Deleting %d task definitions in chunks of size %d...",
            len(expired_taskdef_arns),
            _DELETE_CHUNK_SIZE,
        )
        for idx, chunk in enumerate(_chunker(expired_taskdef_arns, _DELETE_CHUNK_SIZE)):
            if not dry_run:
                ecs.delete_task_definitions(taskDefinitions=chunk)

            logger.warning("Deleted %d task definitions in %d-th batch.", len(chunk), idx)


def _chunker(sequence: list, size: int) -> Iterator[list]:
    """Yield successive chunks of a given size from the sequence."""
    for i in range(0, len(sequence), size):
        yield sequence[i : i + size]
