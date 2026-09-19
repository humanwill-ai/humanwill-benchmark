"""Version 2 configuration; explicit prices, routes and credential references.

Version 1 stays independently readable in config.py. No secrets or network reads.
"""
from dataclasses import dataclass
from pathlib import Path
import re
from .contracts import fields, identifier, nonempty, require, encode, decode, HumanWillError


def clone(value):
    try: return decode(encode(value))
    except (ValueError, TypeError, RecursionError):
        raise HumanWillError("invalid_config", "Configuration must contain finite JSON-compatible values.") from None


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, message="Integer outside supported limits.")
    return value


def spec(value, *, judge=False):
    fields(value, {"id", "provider", "model"}, {"credential", "returned_models", "route", "returned_providers",
        "max_output_tokens", "max_input_tokens", "timeout_seconds", "settings", "prices", "fail_cases", "abstain_fr_cases"})
    result = clone(value)
    identifier(result["id"])
    provider = result["provider"]
    require(provider in {"mock", "openai", "anthropic", "openrouter"}, "unsupported_provider", "Unsupported provider.")
    nonempty(result["model"])
    if provider == "mock":
        require(set(result) <= {"id", "provider", "model", "fail_cases", "abstain_fr_cases"}, message="Unsupported mock settings.")
        require(result["model"] in ({"exact"} if judge else {"echo", "refuse"}), message="Unsupported mock model.")
        for key in ("fail_cases", "abstain_fr_cases"):
            result.setdefault(key, [])
            require(isinstance(result[key], list), message="Expected case array.")
            for item in result[key]: identifier(item)
            require(len(result[key]) == len(set(result[key])), message="Duplicate case selection.")
        require(judge or not result["abstain_fr_cases"], message="Only judges can abstain.")
        return result
    require(not ({"fail_cases", "abstain_fr_cases"} & result.keys()), message="Mock controls cannot configure live models.")
    credential = result.get("credential")
    require(isinstance(credential, str) and (re.fullmatch(r"env:[A-Z][A-Z0-9_]{0,79}", credential)
            or credential == "keychain:" + provider), message="Use an env:VARIABLE or keychain:provider reference.")
    for key, default, low, high in (("max_output_tokens", 8192, 1, 131072), ("max_input_tokens", 272000, 1, 2000000),
                                   ("timeout_seconds", 240, 1, 3600)):
        result[key] = integer(result.get(key, default), low, high)
    result.setdefault("returned_models", [result["model"]])
    for key in ("returned_models", "returned_providers"):
        if key in result:
            require(isinstance(result[key], list) and result[key], message="Expected explicit returned identities.")
            for item in result[key]: nonempty(item)
            require(len(set(result[key])) == len(result[key]), message="Duplicate returned identity.")
    if provider == "openrouter":
        nonempty(result.get("route"))
        require(isinstance(result.get("returned_providers"), list), message="OpenRouter requires returned provider identities.")
    else:
        require(not ({"route", "returned_providers"} & result.keys()), message="Routing belongs to OpenRouter only.")
    options = result.setdefault("settings", {})
    allowed = {"openai": {"reasoning_effort", "temperature"},
               "anthropic": {"thinking", "effort", "temperature"},
               "openrouter": {"reasoning_effort", "temperature"}}[provider]
    fields(options, set(), allowed)
    if "reasoning_effort" in options:
        require(options["reasoning_effort"] in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}, message="Unsupported effort.")
    if "temperature" in options:
        temp = options["temperature"]
        require(type(temp) in (int, float) and 0 <= temp <= 2, message="Invalid temperature.")
    if "thinking" in options:
        require(options["thinking"] in {"adaptive", "disabled"}, message="Unsupported thinking mode.")
    if "effort" in options:
        require(options["effort"] in {"low", "medium", "high", "max"}, message="Unsupported effort.")
    prices = result.get("prices")
    fields(prices, {"input_micro_usd_per_million", "output_micro_usd_per_million", "source", "verified_at"})
    for key in ("input_micro_usd_per_million", "output_micro_usd_per_million"):
        integer(prices[key], 1, 100000000000)
    nonempty(prices["source"])
    from datetime import date
    try: date.fromisoformat(prices["verified_at"])
    except (TypeError, ValueError): require(False, message="Price date must be YYYY-MM-DD.")
    return result


@dataclass(frozen=True)
class Settings:
    serialized: bytes
    def to_dict(self): return decode(self.serialized)
    @property
    def workspace(self): return self.to_dict()["workspace"]
    @property
    def pack(self): return self.to_dict()["pack"]


def from_dict(value, *, base: Path):
    fields(value, {"version", "pack", "workspace", "models", "judge", "budget_micro_usd"},
           {"concurrency", "minimum_interval_ms", "judge_policy", "policy_bundle", "case_ids", "native_block_scoring"})
    require(type(value["version"]) is int and value["version"] == 2, message="Expected config version 2.")
    result = clone(value)
    require(isinstance(value["models"], list) and value["models"], message="Select models.")
    result["models"] = [spec(m) for m in value["models"]]
    require(len({m["id"].casefold() for m in result["models"]}) == len(result["models"]), message="Duplicate model ID.")
    result["judge"] = spec(value["judge"], judge=True)
    if 'native_block_scoring' in result:
        from .grading import NATIVE_RULE
        require(result['native_block_scoring']==NATIVE_RULE and result['judge']['provider']!='mock',
                message='native_block_scoring requires native-block-fr-u/1 and a live judge.')
    result["concurrency"] = integer(value.get("concurrency", 1), 1, 16)
    result["minimum_interval_ms"] = integer(value.get("minimum_interval_ms", 0), 0, 60000)
    live = any(m["provider"] != "mock" for m in [*result["models"], result["judge"]])
    integer(result["budget_micro_usd"], 1 if live else 0, 1000000000000)
    require(not live or result["judge"]["provider"] != "mock", message="Live answers require a semantic judge.")
    require(not ('judge_policy' in result and 'policy_bundle' in result), message='Choose judge_policy or policy_bundle, not both.')
    require('policy_bundle' not in result or result['judge']['provider'] != 'mock', message='Policy bundles require a semantic judge; mock scoring cannot apply them.')
    if result["judge"]["provider"] != "mock":
        nonempty(result.get("policy_bundle", result.get("judge_policy")))
    for key in ("pack", "workspace", "judge_policy", "policy_bundle"):
        if key not in result: continue
        nonempty(result[key])
        require("://" not in result[key], message="Expected local path.")
        result[key] = str((base / Path(result[key]).expanduser()).resolve())
    result.setdefault("case_ids", [])
    require(isinstance(result["case_ids"], list), message="Expected case IDs array.")
    for item in result["case_ids"]: identifier(item)
    require(len(result["case_ids"]) == len(set(result["case_ids"])), message="Duplicate selected case.")
    return Settings(encode(result))
