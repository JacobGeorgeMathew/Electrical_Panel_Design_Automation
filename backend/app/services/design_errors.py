from typing import Any, Dict, List, Optional


class DesignError(Exception):
    """Expected, user-correctable failure while generating an engineering design."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None,
                 errors: Optional[List[str]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.errors = errors or []

    def as_dict(self) -> Dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message,
                           "details": self.details, "errors": self.errors}}
