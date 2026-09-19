"""Versioned data primitives. Errors deliberately exclude input payloads."""
from dataclasses import dataclass
import hashlib
import json
import re


class HumanWillError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 2):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def require(condition, code="invalid_input", message="Invalid input."):
    if not condition:
        raise HumanWillError(code, message)


def fields(value, required, optional=()):
    require(isinstance(value, dict), message="Expected an object.")
    require(set(required) <= value.keys() <= set(required) | set(optional),
            message="Missing or unsupported fields.")


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value),
            message="IDs require 1–80 letters, digits, underscores or hyphens.")
    return value


def nonempty(value):
    require(isinstance(value, str) and bool(value.strip()), message="Expected nonempty text.")
    return value


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return digest(encode(value))


def text_digest(value):
    return digest(value.encode("utf-8"))


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, message="Duplicate JSON key.")
            result[key] = value
        return result

    def invalid_constant(_):
        raise HumanWillError("invalid_input", "Non-finite JSON number.")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise HumanWillError("invalid_input", "Invalid JSON document.") from exc


@dataclass(frozen=True)
class Plan:
    """Immutable serialized plan; to_dict() returns an independent copy."""
    serialized: bytes

    def to_dict(self):
        return decode(self.serialized)

    @property
    def run_id(self):
        return self.to_dict()["run_id"]


def envelope(operation, data=None, error=None):
    return {"format": "humanwill.cli/1", "operation": operation,
            "ok": error is None, "data": data,
            "error": None if error is None else {"code": error.code, "message": str(error)}}
