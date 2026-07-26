"""Session budget management — tracks node budget per investigation."""


class BudgetManager:
    """Encapsulates investigation budget tracking.

    The budget is the kernel's hard termination guarantee (invariant 7).
    A BudgetManager owns one investigation's spend; it is never shared.
    """

    def __init__(self, total: int, warn_fraction: float = 0.25) -> None:
        if total <= 0:
            raise ValueError(f"budget total must be positive, got {total}")
        self._total = total
        self._remaining = total
        self._warn_fraction = warn_fraction

    def consume(self, cost: int = 1) -> bool:
        """Deduct `cost` from the budget.
        Returns False if already exhausted (caller should stop)."""
        if self._remaining <= 0:
            return False
        self._remaining = max(0, self._remaining - cost)
        return True

    @property
    def remaining(self) -> int:
        return self._remaining

    @property
    def used(self) -> int:
        return self._total - self._remaining

    @property
    def total(self) -> int:
        return self._total

    def is_exhausted(self) -> bool:
        return self._remaining <= 0

    def is_low(self) -> bool:
        """True when remaining budget is within the warning fraction."""
        return self._remaining <= int(self._total * self._warn_fraction)
