from typing import NamedTuple


class ECSServiceRef(NamedTuple):
    """Reference to an ECS service."""

    cluster: str
    service: str
