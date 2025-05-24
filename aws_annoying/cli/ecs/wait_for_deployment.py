from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import typer

from aws_annoying.ecs import DeploymentFailedError, ECSDeploymentWaiter, ECSServiceRef
from aws_annoying.utils.timeout import OperationTimeoutError, Timeout

from ._app import ecs_app

logger = logging.getLogger(__name__)


@ecs_app.command()
def wait_for_deployment(  # noqa: PLR0913
    *,
    cluster: str = typer.Option(
        ...,
        help="The name of the ECS cluster.",
        show_default=False,
    ),
    service: str = typer.Option(
        ...,
        help="The name of the ECS service.",
        show_default=False,
    ),
    expected_task_definition: Optional[str] = typer.Option(
        None,
        help=(
            "The service's task definition expected after deployment."
            " If provided, it will be used to assert the service's task definition after deployment finished or timed out."  # noqa: E501
        ),
        show_default=False,
    ),
    polling_interval: int = typer.Option(
        5,
        help="The interval between any polling attempts, in seconds.",
        min=1,
    ),
    timeout_seconds: Optional[int] = typer.Option(
        None,
        help=(
            "The maximum time to wait for the deployment to complete, in seconds."
            " If not provided, it will wait indefinitely."
        ),
        min=1,
    ),
    wait_for_start: bool = typer.Option(
        True,  # noqa: FBT003
        help=(
            "Whether to wait for the deployment to start."
            " Because there could be no deployment right after the deploy,"
            " this option will wait for a new deployment to start if no running deployment is found."
        ),
    ),
    wait_for_stability: bool = typer.Option(
        False,  # noqa: FBT003
        help="Whether to wait for the service to be stable after the deployment.",
    ),
) -> None:
    """Wait for ECS deployment to complete."""
    start = datetime.now(tz=timezone.utc)
    waiter = ECSDeploymentWaiter(ECSServiceRef(cluster=cluster, service=service))
    try:
        with Timeout(timeout_seconds):
            waiter.wait(
                wait_for_start=wait_for_start,
                polling_interval=polling_interval,
                wait_for_stability=wait_for_stability,
                expected_task_definition=expected_task_definition,
            )
    except OperationTimeoutError:
        logger.error(  # noqa: TRY400
            "Timeout reached after %s seconds. The deployment may not have finished.",
            timeout_seconds,
        )
        raise typer.Exit(1) from None
    except DeploymentFailedError as err:
        elapsed = datetime.now(tz=timezone.utc) - start
        logger.error(  # noqa: TRY400
            "Deployment failed in [bold]%s[/bold] seconds with error: %s",
            elapsed.total_seconds(),
            err,
        )
        raise typer.Exit(1) from None

    elapsed = datetime.now(tz=timezone.utc) - start
    logger.info(
        "Deployment succeeded in [bold]%s[/bold] seconds.",
        elapsed.total_seconds(),
    )
