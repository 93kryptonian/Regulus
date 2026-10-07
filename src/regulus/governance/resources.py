import json
from importlib import resources

from .access import Matrix
from .retention import Policy


def text(name: str) -> str:
    return resources.files("regulus.governance").joinpath("data", name).read_text(encoding="utf-8")


def default_matrix() -> Matrix:
    return Matrix.model_validate(json.loads(text("access_matrix.v1.json")))


def default_policy() -> Policy:
    return Policy.model_validate(json.loads(text("retention_policy.v1.json")))


def default_inventory() -> list[dict[str, object]]:
    data = json.loads(text("data_inventory.v1.json"))
    assert isinstance(data, list)
    return data


def default_controls() -> dict[str, object]:
    data = json.loads(text("controls_map.v1.json"))
    assert isinstance(data, dict)
    return data
