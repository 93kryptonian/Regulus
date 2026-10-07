import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock"
HEADER = "# runtime dependency closure of regulus; regenerate with scripts/lock.py\n"


def declared(name: str = "regulus") -> list[Requirement]:
    return [Requirement(r) for r in metadata.requires(name) or [] if "extra ==" not in r]


def closure(roots: list[Requirement]) -> dict[str, str]:
    found: dict[str, str] = {}
    todo = list(roots)
    while todo:
        req = todo.pop()
        if req.marker and not req.marker.evaluate({"extra": ""}):
            continue
        key = canonicalize_name(req.name)
        if key in found:
            continue
        dist = metadata.distribution(req.name)
        found[key] = dist.version
        todo += [Requirement(r) for r in dist.requires or [] if "extra ==" not in r]
    return dict(sorted(found.items()))


def render(pins: dict[str, str]) -> str:
    return HEADER + "".join(f"{k}=={v}\n" for k, v in pins.items())


def parse(text: str) -> dict[str, str]:
    rows = [ln.split("==") for ln in text.splitlines() if ln and not ln.startswith("#")]
    return {k: v for k, v in rows}


def main() -> int:
    LOCK.write_text(render(closure(declared())), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
