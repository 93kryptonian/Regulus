import json
import re
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import Field, ValidationError, model_validator

from regulus.domain.base import Model
from regulus.workflow.schedule import ScheduleConfig

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
SECRET_KEY = re.compile(r"secret|token|password|key", re.IGNORECASE)
SECRET_ENV = "REGULUS_CSRF_SECRET"
ENV = {
    "REGULUS_HOST": "host",
    "REGULUS_PORT": "port",
    "REGULUS_STATE_DIR": "state_dir",
    "REGULUS_AUTH_MODE": "auth_mode",
    "REGULUS_CLAIM_TTL_SECONDS": "claim_ttl_seconds",
    "REGULUS_OBSERVATION_BUFFER": "observation_buffer",
    "REGULUS_RETENTION_POLICY": "retention_policy",
    "REGULUS_PRICE_TABLE": "price_table",
}
INTS = {"port", "claim_ttl_seconds", "observation_buffer"}
STRS = {"host", "state_dir", "auth_mode", "retention_policy", "price_table", "csrf_secret"}


class ConfigError(Exception):
    def __init__(self, problems: list[tuple[str, str]]) -> None:
        self.problems = problems
        super().__init__("; ".join(f"{f}: {r}" for f, r in problems))


class AuthMode(StrEnum):
    NONE = "none"
    DEV_HEADER = "dev_header"
    EXTERNAL = "external"


class RegulusConfig(Model):
    host: str = "127.0.0.1"
    port: int = Field(8765, ge=1, le=65535)
    state_dir: Path = Path("regulus-state")
    auth_mode: AuthMode = AuthMode.NONE
    claim_ttl_seconds: int = Field(900, gt=0)
    schedule: ScheduleConfig = ScheduleConfig()
    observation_buffer: int = Field(1000, gt=0)
    retention_policy: Path | None = None
    price_table: Path | None = None
    csrf_secret: str = Field(repr=False, exclude=True, min_length=32)

    @model_validator(mode="after")
    def _bind(self) -> "RegulusConfig":
        if self.host not in LOOPBACK and self.auth_mode is not AuthMode.EXTERNAL:
            raise ValueError("non-loopback host requires auth_mode external")
        return self

    def effective(self) -> dict[str, object]:
        out = json.loads(self.model_dump_json())
        out["csrf_secret"] = "<set>"
        return out  # type: ignore[no-any-return]


def _problems(e: ValidationError) -> list[tuple[str, str]]:
    out = []
    for x in e.errors():
        field = ".".join(str(p) for p in x["loc"])
        if x["type"] == "value_error":
            out.append((field or "host", str(x["ctx"]["error"])))
        else:
            out.append((field or "config", x["type"]))
    return out


def load(path: Path | None = None, env: Mapping[str, str] | None = None) -> RegulusConfig:
    env = env or {}
    raw: dict[str, object] = {}
    problems: list[tuple[str, str]] = []
    if path is not None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ConfigError([("config_file", "unreadable_or_invalid_json")]) from None
        if not isinstance(data, dict):
            raise ConfigError([("config_file", "must_be_object")])
        for k in data:
            if SECRET_KEY.search(k):
                problems.append((k, "secret_in_file_forbidden"))
        for k in sorted(STRS & data.keys()):
            if not isinstance(data[k], str) and not (
                data[k] is None and k in ("retention_policy", "price_table")
            ):
                problems.append((k, "must_be_string"))
        for k in sorted(INTS & data.keys()):
            if type(data[k]) is not int:
                problems.append((k, "must_be_integer"))
        raw = data
    for var, field in ENV.items():
        if var in env:
            v: object = env[var]
            if field in INTS:
                if not re.fullmatch(r"-?\d{1,9}", str(v)):
                    problems.append((field, "int_parsing"))
                    continue
                v = int(str(v))
            raw[field] = v
    if problems:
        raise ConfigError(problems)
    if SECRET_ENV in env:
        raw["csrf_secret"] = env[SECRET_ENV]
    try:
        return RegulusConfig.model_validate_json(json.dumps(raw, default=str), strict=True)
    except ValidationError as e:
        raise ConfigError(_problems(e)) from None
