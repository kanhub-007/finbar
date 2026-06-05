"""ConditionTreeVisitor interface for traversing v2 condition trees."""

from abc import ABC, abstractmethod

from finbar.core.domain.entities.condition import Condition
from finbar.core.domain.entities.condition_group import ConditionGroup


class ConditionTreeVisitor(ABC):
    """Base visitor for v2 strategy condition trees."""

    def visit_group(self, group: ConditionGroup | None) -> None:
        """Visit a group and recursively traverse its children."""
        if group is None:
            return
        if group.condition is not None:
            self.visit_condition(group.condition)
        for child in group.children:
            self.visit_group(child)

    @abstractmethod
    def visit_condition(self, condition: Condition) -> None:
        """Visit an atomic condition."""
