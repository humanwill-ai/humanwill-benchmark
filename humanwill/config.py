"""Strict TOML configuration; version 1 offline and version 2 execution settings."""
from dataclasses import asdict, dataclass
from pathlib import Path
import tomllib

from .contracts import HumanWillError, fields, identifier, require


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str = "mock"
    model: str = "echo"
    fail_cases: tuple[str, ...] = ()
    abstain_fr_cases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunConfig:
    pack: str
    workspace: str
    models: tuple[ModelSpec, ...]
    judge: ModelSpec
    concurrency: int = 1
    version: int = 1

    def to_dict(self):
        value = asdict(self)
        value["models"] = [asdict(m) for m in self.models]
        for spec in [*value["models"], value["judge"]]:
            spec["fail_cases"] = list(spec["fail_cases"])
            spec["abstain_fr_cases"] = list(spec["abstain_fr_cases"])
        return value


def model_spec(value, *, judge=False):
    fields(value, {"id", "provider", "model"}, {"fail_cases", "abstain_fr_cases"})
    identifier(value["id"])
    require(value["provider"] == "mock", "unsupported_provider",
            "This milestone supports only the offline mock provider.")
    choices = {"exact"} if judge else {"echo", "refuse"}
    require(isinstance(value["model"], str) and value["model"] in choices,
            "unsupported_model", "Unsupported mock model.")
    for key in ("fail_cases", "abstain_fr_cases"):
        items = value.get(key, [])
        require(isinstance(items, list), message="Case selections must be arrays.")
        for item in items:
            identifier(item)
        require(len(items) == len(set(items)), message="Duplicate selected case ID.")
    require(judge or not value.get("abstain_fr_cases"), message="FR abstention is a judge setting.")
    return ModelSpec(value["id"], value["provider"], value["model"],
                     tuple(value.get("fail_cases", [])), tuple(value.get("abstain_fr_cases", [])))


def from_dict(value, *, base: Path):
    if isinstance(value, dict) and value.get("version") == 2:
        from .settings import from_dict as v2
        return v2(value, base=base)
    fields(value, {"version", "pack", "workspace", "models", "judge"}, {"concurrency"})
    require(type(value["version"]) is int and value["version"] == 1,
            "unsupported_version", "Unsupported configuration version.")
    concurrency = value.get("concurrency", 1)
    require(type(concurrency) is int and 1 <= concurrency <= 16,
            message="Concurrency must be an integer from 1 to 16.")
    require(isinstance(value["models"], list) and bool(value["models"]), message="Select at least one model.")
    models = tuple(model_spec(m) for m in value["models"])
    require(len({m.id.casefold() for m in models}) == len(models), message="Duplicate model ID.")
    paths = {}
    for key in ("pack", "workspace"):
        item = value[key]
        require(isinstance(item, str) and bool(item.strip()), message="Expected a local path.")
        require("://" not in item, message="Only local paths are supported.")
        path = Path(item).expanduser()
        paths[key] = str((base / path).resolve())
    return RunConfig(**paths, models=models, judge=model_spec(value["judge"], judge=True),
                     concurrency=concurrency)


def load(config: str | Path | RunConfig):
    from .settings import Settings
    if isinstance(config, (RunConfig, Settings)):
        return from_dict(config.to_dict(), base=Path.cwd())
    path = Path(config).expanduser().resolve()
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise HumanWillError("invalid_config", "Cannot read a valid TOML configuration.") from exc
    return from_dict(value, base=path.parent)
