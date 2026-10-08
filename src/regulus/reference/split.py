import json
from pathlib import Path

from .models import ReferenceCorpus, Role, Split


def load_split(path: Path) -> Split:
    return Split.model_validate(json.loads(path.read_text(encoding="utf-8")))


def split_problems(corpus: ReferenceCorpus, split: Split) -> list[str]:
    problems: list[str] = []
    seen: dict[str, Role] = {}
    for a in split.assignments:
        if a.regulation_id in seen:
            problems.append(f"{a.regulation_id}: assigned more than once")
        seen[a.regulation_id] = a.role
    ids = {r.regulation_id for r in corpus.regulations}
    problems += [f"{i}: in the corpus but not in the split" for i in sorted(ids - set(seen))]
    problems += [f"{i}: in the split but not in the corpus" for i in sorted(set(seen) - ids)]
    if len(split.ids(Role.TEST)) < 2:
        problems.append("the test role needs at least two regulations")
    if not split.ids(Role.DEV):
        problems.append("the dev role is empty")
    for role in Role:
        want = split.expected_obligations.get(role.value)
        got = sum(len(corpus.obligations_of(i)) for i in split.ids(role))
        if want is not None and want != got:
            problems.append(f"{role.value}: expected {want} derived obligations, found {got}")
    return problems
