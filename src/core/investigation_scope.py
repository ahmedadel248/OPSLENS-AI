from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InvestigationScope:
    """
    User-selected investigation scope.

    v1 mode:
    - node_name is required
    - namespace is required

    This keeps every agent focused and prevents cluster-wide noisy scans.
    """

    node_name: str
    namespace: str

    def validate(self) -> None:
        if not self.node_name:
            raise ValueError("node_name is required for focused investigation.")

        if not self.namespace:
            raise ValueError("namespace is required for focused investigation.")


