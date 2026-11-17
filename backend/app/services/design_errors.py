from typing import Any, Dict, List, Optional
from app.observability import public, correlation, safe_code


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
        return {"error": {"code": safe_code(self.code), "message": public(self.message),
                           "details": public(self.details), "errors": public(self.errors),
                           "correlation": correlation()}}
