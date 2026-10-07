from pathlib import Path

from regulus.observability.demo import SCOPE, run
from regulus.observability.scan import scan


def test_the_demo_is_deterministic_private_and_states_its_scope(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    run(a)
    run(b)
    names = sorted(p.name for p in a.iterdir())
    assert names == ["cost.json", "events.jsonl", "metrics.txt", "summary.md"]
    for n in names:
        assert (a / n).read_text(encoding="utf-8") == (b / n).read_text(encoding="utf-8")
    arts = {n: (a / n).read_text(encoding="utf-8") for n in names}
    assert scan(arts, ["Pengendali wajib menyimpan arsip"]) == []
    assert SCOPE in arts["summary.md"] and "No production traffic" in arts["summary.md"]
    assert "AI calls" in arts["cost.json"] and "1 unpriced" in arts["cost.json"]
