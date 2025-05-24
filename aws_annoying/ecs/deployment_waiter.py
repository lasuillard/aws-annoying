from __future__ import annotations

import logging
from time import sleep
from typing import TYPE_CHECKING, Optional

import boto3
import botocore.exceptions
import typer
from pydantic import PositiveInt, validate_call

if TYPE_CHECKING:
    from .common import ECSServiceRef

logger = logging.getLogger(__name__)


class DeploymentFailedError(Exception):
    """Deployment failed."""


class ECSDeploymentWaiter:
    """ECS service deployment waiter."""

    def __init__(self, service_ref: ECSServiceRef, *, session: boto3.session.Session | None = None) -> None:
        """Initialize instance.

        Args:
            service_ref: Reference to the ECS service.
            session: Boto3 session to use for AWS operations.

        """
        self.service_ref = service_ref
        self.session = session or boto3.session.Session()

    @validate_call
    def wait(
        self,
        *,
        wait_for_start: bool,
        polling_interval: PositiveInt = 5,
        wait_for_stability: bool,
        expected_task_definition: Optional[str] = None,
    ) -> None:
        """Wait for the ECS deployment to complete.

        Args:
            wait_for_start: Whether to wait for the deployment to start.
            polling_interval: The interval between any polling attempts, in seconds.
            wait_for_stability: Whether to wait for the service to be stable after the deployment.
            expected_task_definition: The service's task definition expected after deployment.
        """
        # Find current deployment for the service
        logger.info(
            "Looking up running deployment for service [bold]%s[/bold]",
            self.service_ref.service,
        )
        latest_deployment_arn = self.get_latest_deployment_arn(
            wait_for_start=wait_for_start,
            polling_interval=polling_interval,
        )

        # Polling for the deployment to finish (successfully or unsuccessfully)
        logger.info(
            "Start waiting for deployment [bold]%s[/bold] to finish.",
            latest_deployment_arn,
        )
        ok, status = self.wait_for_deployment_complete(latest_deployment_arn, polling_interval=polling_interval)
        if ok:
            logger.info(
                "Deployment succeeded with status [bold green]%s[/bold green]",
                status,
            )
        else:
            msg = f"Deployment failed with status: {status}"
            raise DeploymentFailedError(msg)

        # Wait for the service to be stable
        if wait_for_stability:
            logger.debug(
                "Waiting for service [bold]%s[/bold] to be stable.",
                self.service_ref.service,
            )
            self.wait_for_service_stability(polling_interval=polling_interval)

        # Check if the service task definition matches the expected one
        if expected_task_definition:
            logger.info(
                "Checking if the service task definition is the expected one: [bold]%s[/bold]",
                expected_task_definition,
            )
            ok, actual = self.assert_service_task_definition_is(expect=expected_task_definition)
            if ok:
                logger.info("The service task definition matches the expected one.")
            else:
                logger.error(
                    "The service task definition is not the expected one; got: [bold red]%s[/bold red]",
                    actual,
                )
                raise typer.Exit(1)

    @validate_call
    def get_latest_deployment_arn(
        self,
        *,
        wait_for_start: bool,
        polling_interval: PositiveInt,
        max_attempts: Optional[PositiveInt] = None,
    ) -> str:
        """Get the latest deployment ARN for the service.

        Args:
            wait_for_start: Whether to wait for the deployment to start.
            polling_interval: The interval between any polling attempts, in seconds.
            max_attempts: The maximum number of attempts to wait for the deployment to start.

        Returns:
            The ARN of the latest deployment for the service.
        """
        ecs = self.session.client("ecs")

        attempts = 0
        while (max_attempts is None) or (attempts <= max_attempts):
            running_deployments = ecs.list_service_deployments(
                cluster=self.service_ref.cluster,
                service=self.service_ref.service,
                status=["PENDING", "IN_PROGRESS"],
            )["serviceDeployments"]
            if running_deployments:
                break

            if wait_for_start:
                logger.info(
                    "(%d-th attempt) No running deployments found for service [bold]%s[/bold]. Waiting for a new deployment.",  # noqa: E501
                    attempts + 1,
                    self.service_ref.service,
                )
            else:
                logger.error(
                    "No running deployments found for service [bold]%s[/bold]. Exiting.",
                    self.service_ref.service,
                )
                raise typer.Exit(0)

            sleep(polling_interval)
            attempts += 1

        return running_deployments[0]["serviceDeploymentArn"]

    @validate_call
    def wait_for_deployment_complete(
        self,
        deployment_arn: str,
        *,
        polling_interval: PositiveInt,
        max_attempts: Optional[PositiveInt] = None,
    ) -> tuple[bool, str]:
        """Wait for the ECS deployment to complete.

        Args:
            deployment_arn: The ARN of the deployment to wait for.
            polling_interval: The interval between any polling attempts, in seconds.
            max_attempts: The maximum number of attempts to wait for the deployment to complete.

        Returns:
            A tuple containing a boolean indicating whether the deployment succeeded and the status of the deployment.
        """
        ecs = self.session.client("ecs")

        attempts = 0
        while (max_attempts is None) or (attempts <= max_attempts):
            latest_deployment = ecs.describe_service_deployments(serviceDeploymentArns=[deployment_arn])[
                "serviceDeployments"
            ][0]
            status = latest_deployment["status"]
            if status == "SUCCESSFUL":
                return (True, status)

            if status in ("PENDING", "IN_PROGRESS"):
                logger.debug(
                    "(%d-th attempt) Deployment in progress... [bold grey53]%s[/bold grey53]",
                    attempts + 1,
                    status,
                )
            else:
                break

            sleep(polling_interval)
            attempts += 1

        return (False, status)

    @validate_call
    def wait_for_service_stability(
        self,
        *,
        polling_interval: PositiveInt,
        max_attempts: Optional[PositiveInt] = None,
    ) -> bool:
        """Wait for the ECS service to be stable.

        Args:
            polling_interval: The interval between any polling attempts, in seconds.
            max_attempts: The maximum number of attempts to wait for the service to be stable.

        Returns:
            A boolean indicating whether the service is stable.
        """
        ecs = self.session.client("ecs")

        # TODO(lasuillard): Likely to be a problem in some cases: https://github.com/boto/botocore/issues/3314
        stability_waiter = ecs.get_waiter("services_stable")

        attempts = 0
        while (max_attempts is None) or (attempts <= max_attempts):
            logger.debug(
                "(%d-th attempt) Waiting for service [bold]%s[/bold] to be stable...",
                attempts + 1,
                self.service_ref.service,
            )
            try:
                stability_waiter.wait(
                    cluster=self.service_ref.cluster,
                    services=[self.service_ref.service],
                    WaiterConfig={"Delay": polling_interval, "MaxAttempts": 1},
                )
            except botocore.exceptions.WaiterError as err:
                if err.kwargs["reason"] != "Max attempts exceeded":
                    raise
            else:
                return True

            sleep(polling_interval)
            attempts += 1

        return False

    @validate_call
    def assert_service_task_definition_is(self, *, expect: str) -> tuple[bool, str]:
        """Assert the service task definition.

        Args:
            expect: The ARN of expected task definition.
        """
        ecs = self.session.client("ecs")

        logger.info(
            "Checking if the service task definition is the expected one: [bold]%s[/bold]",
            expect,
        )
        service_detail = ecs.describe_services(cluster=self.service_ref.cluster, services=[self.service_ref.service])[
            "services"
        ][0]
        ok = service_detail["taskDefinition"] == expect
        current_task_definition_arn = service_detail["taskDefinition"]
        return (ok, current_task_definition_arn)
