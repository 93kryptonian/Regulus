from pathlib import Path

from ing_helpers import READER, REG, fresh, pdf

from regulus.ingestion.ingest import ingest

SRC = Path(__file__).parents[2] / "src" / "regulus" / "ingestion"


def test_no_ingestion_module_imports_the_reference_or_a_model_or_a_database():
    text = "\n".join(p.read_text(encoding="utf-8") for p in SRC.glob("*.py"))
    for forbidden in (
        "regulus.reference",
        "openai",
        "psycopg",
        "supabase",
        "requests",
        "urllib",
        "socket",
    ):
        assert forbidden not in text, forbidden


def test_ingestion_is_deterministic():
    a = ingest(pdf(glitch={3: "Pasa13"}), REG, READER, fresh())
    b = ingest(pdf(glitch={3: "Pasa13"}), REG, READER, fresh())
    assert a == b and a.model_dump_json() == b.model_dump_json()


def test_the_phase_3_processor_is_called_unchanged():
    import regulus.ingestion.ingest as m
    from regulus.documents import process

    assert m.process is process
