from typing import Optional
class AutomationError(Exception):
    """Custom exception for automation-related errors."""
    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)