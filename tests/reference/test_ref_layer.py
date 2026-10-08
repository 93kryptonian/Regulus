import shutil

from ref_helpers import ROOT

from regulus.evaluation.builder import Builder
from regulus.evaluation.layers import reference
from regulus.evaluation.models import GateKind, Status


def build(root):
    b = Builder()
    reference.evaluate(b, root / "evaluation")
    return b


def test_without_the_local_reference_real_rows_are_not_measurable_and_standin_rows_run(tmp_path):
    (tmp_path / "evaluation").mkdir()
    shutil.copy(ROOT / "evaluation" / "reference_split.v1.json", tmp_path / "evaluation")
    b = build(tmp_path)
    st = {k: r.status for k, r in b.results.items()}
    assert (
        st["reference.instrument_failures"] is Status.OK
        and st["reference.nondeterministic_builds"] is Status.OK
    )
    real = [
        k
        for k in st
        if k
        in {
            f"reference.{x}"
            for x in (
                "instrument_failures_real",
                "split_violations",
                "content_leaks",
                "tracked_reference_files",
                "unknown_sector_links",
                "parse_error_rows",
                "count_unreconciled_regulations",
            )
        }
    ]
    assert real and all(st[k] is Status.NOT_MEASURABLE for k in real)
    assert b.populations["reference_real.regulations"].n == 0


def test_unlabelled_dimensions_are_never_scored(tmp_path):
    (tmp_path / "evaluation").mkdir()
    shutil.copy(ROOT / "evaluation" / "reference_split.v1.json", tmp_path / "evaluation")
    b = build(tmp_path)
    for k in ("type_accuracy", "sanction_accuracy", "appendix_accuracy", "pointer_accuracy"):
        r = b.results[f"reference.{k}"]
        assert r.status is Status.NOT_MEASURABLE and "no labels" in r.note


def test_hard_gates_are_zero_and_the_count_row_is_report_only(tmp_path):
    (tmp_path / "evaluation").mkdir()
    shutil.copy(ROOT / "evaluation" / "reference_split.v1.json", tmp_path / "evaluation")
    b = build(tmp_path)
    hard = [
        d for d in b.definitions.values() if d.gate is not None and d.gate.kind is GateKind.HARD
    ]
    assert len(hard) == 9 and all(d.gate.expect == 0.0 for d in hard)
    assert b.definitions["reference.count_unreconciled_regulations"].gate is None
