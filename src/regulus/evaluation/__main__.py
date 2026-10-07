import subprocess
import sys
from pathlib import Path

from .runner import run


def main() -> int:
    root = Path("evaluation")
    try:
        ref = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        ref = "unversioned"
    return run(root, Path("pdf"), root / "reports", ref, root / "baseline.v1.json")


if __name__ == "__main__":
    sys.exit(main())
