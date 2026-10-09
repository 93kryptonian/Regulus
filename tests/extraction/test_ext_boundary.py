import ast
from pathlib import Path

import regulus.extraction as pkg

FORBIDDEN = {
    "openai",
    "httpx",
    "requests",
    "urllib",
    "socket",
    "http",
    "psycopg",
    "psycopg2",
    "supabase",
    "sqlite3",
    "regulus.reference",
}


def test_no_model_network_database_or_reference_imports() -> None:
    root = Path(pkg.__file__).parent
    files = sorted(root.glob("*.py"))
    assert len(files) >= 6
    for f in files:
        for node in ast.walk(ast.parse(f.read_text())):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for n in names:
                assert not any(n == b or n.startswith(b + ".") for b in FORBIDDEN), (f.name, n)
