from functools import lru_cache
from wizard_kernel.session.manager import InvestigationManager


@lru_cache(maxsize=1)
def get_manager() -> InvestigationManager:
    return InvestigationManager()
