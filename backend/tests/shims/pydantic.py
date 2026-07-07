"""Minimal pydantic shim: defaults + nested List[Model] coercion. NOT shipped."""
import typing

class BaseModel:
    def __init__(self, **data):
        hints = typing.get_type_hints(type(self))
        for name, hint in hints.items():
            if name.startswith("_"):
                continue
            if name in data:
                value = data[name]
            elif hasattr(type(self), name):
                value = getattr(type(self), name)
                if isinstance(value, (list, dict, set)):
                    value = type(value)(value)   # fresh copy per instance
            else:
                raise TypeError(f"missing required field: {name}")
            # Coerce List[SubModel] of dicts
            origin = typing.get_origin(hint)
            args = typing.get_args(hint)
            if origin in (list, typing.List) and args and isinstance(args[0], type) \
               and issubclass(args[0], BaseModel) and isinstance(value, list):
                value = [args[0](**v) if isinstance(v, dict) else v for v in value]
            setattr(self, name, value)
