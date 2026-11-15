"""Shared structural validation for versioned documents (no ID allocation)."""
import math
from typing import Annotated, Any, Iterable

from pydantic import BaseModel, BeforeValidator, ConfigDict, model_validator
from pydantic_core import PydanticCustomError


def stable_id(value: Any) -> str:
    # Logical IDs are opaque and scoped; never normalize or derive them from labels.
    if not isinstance(value, str) or not value or value != value.strip() or any(
        ord(char) < 32 or ord(char) == 127 for char in value
    ):
        raise PydanticCustomError('invalid_stable_id', 'Expected a nonempty opaque ID without surrounding whitespace or controls')
    return value


StableID = Annotated[str, BeforeValidator(stable_id)]


def require_reference(value: str, registry: Any, path: str) -> None:
    if value not in registry:
        raise PydanticCustomError('unknown_reference', 'Unknown reference at {path}: {reference}',
                                  {'path': path, 'reference': value})


def unique_ids(values: Iterable[str], path: str) -> set[str]:
    seen: set[str] = set()
    for value in values:
        stable_id(value)
        if value in seen:
            raise PydanticCustomError('duplicate_id', 'Duplicate ID at {path}: {reference}',
                                      {'path': path, 'reference': value})
        seen.add(value)
    return seen


def finite_tree(value: Any, path: str = '$') -> None:
    """Also cover legacy model dictionaries, which allow arbitrary numeric values."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode='python')
    if isinstance(value, float) and not math.isfinite(value):
        raise PydanticCustomError('nonfinite_value', 'Nonfinite number at {path}', {'path': path})
    if isinstance(value, dict):
        for key, item in value.items():
            finite_tree(item, f'{path}.{key}')
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            finite_tree(item, f'{path}[{index}]')


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    @model_validator(mode='before')
    @classmethod
    def finite_values(cls, value: Any) -> Any:
        finite_tree(value)
        return value

    @model_validator(mode='after')
    def finite_parsed_values(self):
        # Legacy nested models can coerce strings to nonfinite floats.
        finite_tree(self)
        return self
